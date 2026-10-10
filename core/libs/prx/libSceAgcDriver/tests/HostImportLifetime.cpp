#include "prx/libSceAgcDriver/Graphics/include/Context.hpp"
#include "prx/libSceAgcDriver/Execution/include/GuestMemory.hpp"
#include "prx/libSceAgcDriver/Graphics/include/GuestBufferMemory.hpp"
#include "prx/libSceAgcDriver/Graphics/include/Recorder.hpp"
#include "prx/libSceAgcDriver/Graphics/include/Resources.hpp"
#include "prx/libc/include/GuestAllocations.hpp"
#include <algorithm>
#include <atomic>
#include <chrono>
#include <future>
#include <cstdio>
#include <cstring>
#include <map>
#include <memory>
#include <mutex>
#include <optional>
#include <new>
#include <stdexcept>
#include <string>
#include <thread>
#include <vector>

namespace {

using namespace AgcDriver::Graphics;
using AgcDriver::GuestMemory::GpuMutex;

template<typename TAction>
std::string failure(TAction action) {
    try { action(); }
    catch (const std::runtime_error& error) { return error.what(); }
    return {};
}

struct ImportState {
    std::atomic<VkBuffer> buffer{VK_NULL_HANDLE};
    VkDeviceMemory memory;
    std::uint64_t address;
    std::size_t bytes;
    std::atomic<bool> destroyed{false};
    std::atomic<unsigned> frees{0};
    std::atomic<bool> outOfOrder{false};
    std::atomic<bool> inaccessible{false};
    std::promise<void> freeing;
    std::shared_future<void> allowFree;
    std::thread::id freeingThread;

    void CheckAccessible() {
        if (!RegisteredReadableCovers(address, bytes) || !AgcDriver::GuestMemory::Accessible(reinterpret_cast<const void*>(address), bytes, false)) inaccessible.store(true);
    }
    void Verify() const {
        Require(frees.load() == 1 && destroyed.load() && !outOfOrder.load(), "host import Vulkan objects were not destroyed exactly once in order before host apply");
        Require(!inaccessible.load(), "guest pages became inaccessible before vkFreeMemory returned");
    }
};

struct Tracking {
    PFN_vkGetDeviceProcAddr resolve;
    VkDevice device;
    std::mutex mutex;
    std::map<VkDeviceMemory, std::shared_ptr<ImportState>> imports;
    std::atomic<bool> failAddressLookup{false};
    std::atomic<bool> failQueueSubmit{false};
    std::atomic<unsigned> rejectedSubmissions{0};
    std::atomic<unsigned> acceptedSubmissions{0};
    std::vector<VkFence> rejectedFences;
    std::shared_ptr<ImportState> lastAllocated;

    std::shared_ptr<ImportState> Find(VkDeviceMemory memory) {
        std::lock_guard lock(mutex);
        const auto found = imports.find(memory);
        return found == imports.end() ? nullptr : found->second;
    }
};

Tracking* tracking = nullptr;
template<typename TFunction>
TFunction original(const char* name) { return reinterpret_cast<TFunction>(tracking->resolve(tracking->device, name)); }

VKAPI_ATTR void VKAPI_CALL destroyBuffer(VkDevice device, VkBuffer buffer, const VkAllocationCallbacks* allocator) {
    original<PFN_vkDestroyBuffer>("vkDestroyBuffer")(device, buffer, allocator);
    std::lock_guard lock(tracking->mutex);
    for (const auto& [memory, state] : tracking->imports) {
        if (state->buffer == buffer && state->frees.load() == 0) state->destroyed.store(true);
    }
}

VKAPI_ATTR void VKAPI_CALL freeMemory(VkDevice device, VkDeviceMemory memory, const VkAllocationCallbacks* allocator) {
    const auto state = tracking->Find(memory);
    if (state != nullptr) {
        if (!state->destroyed.load()) state->outOfOrder.store(true);
        state->CheckAccessible();
        if (state->allowFree.valid()) {
            state->freeingThread = std::this_thread::get_id();
            state->freeing.set_value();
            if (state->allowFree.wait_for(std::chrono::seconds(2)) != std::future_status::ready) state->outOfOrder.store(true);
        }
    }
    original<PFN_vkFreeMemory>("vkFreeMemory")(device, memory, allocator);
    if (state != nullptr) {
        state->CheckAccessible();
        state->frees.fetch_add(1);
    }
}

VKAPI_ATTR VkResult VKAPI_CALL allocateMemory(VkDevice device, const VkMemoryAllocateInfo* allocation, const VkAllocationCallbacks* allocator, VkDeviceMemory* memory) {
    const auto result = original<PFN_vkAllocateMemory>("vkAllocateMemory")(device, allocation, allocator, memory);
    if (result != VK_SUCCESS) return result;
    for (auto* next = static_cast<const VkBaseInStructure*>(allocation->pNext); next != nullptr; next = next->pNext) {
        if (next->sType != VK_STRUCTURE_TYPE_IMPORT_MEMORY_HOST_POINTER_INFO_EXT) continue;
        auto state = std::make_shared<ImportState>();
        state->memory = *memory;
        state->address = reinterpret_cast<std::uint64_t>(reinterpret_cast<const VkImportMemoryHostPointerInfoEXT*>(next)->pHostPointer);
        state->bytes = static_cast<std::size_t>(allocation->allocationSize);
        std::lock_guard lock(tracking->mutex);
        tracking->imports[*memory] = state;
        tracking->lastAllocated = state;
    }
    return result;
}

VKAPI_ATTR VkResult VKAPI_CALL bindBufferMemory(VkDevice device, VkBuffer buffer, VkDeviceMemory memory, VkDeviceSize offset) {
    if (const auto state = tracking->Find(memory)) state->buffer = buffer;
    return original<PFN_vkBindBufferMemory>("vkBindBufferMemory")(device, buffer, memory, offset);
}

VKAPI_ATTR void VKAPI_CALL destroyFence(VkDevice device, VkFence fence, const VkAllocationCallbacks* allocator) {
    original<PFN_vkDestroyFence>("vkDestroyFence")(device, fence, allocator);
    std::lock_guard lock(tracking->mutex);
    std::erase(tracking->rejectedFences, fence);
}

VKAPI_ATTR VkResult VKAPI_CALL queueSubmit(VkQueue queue, std::uint32_t count, const VkSubmitInfo* submissions, VkFence fence) {
    if (tracking->failQueueSubmit.exchange(false)) {
        std::lock_guard lock(tracking->mutex);
        tracking->rejectedFences.push_back(fence);
        tracking->rejectedSubmissions.fetch_add(1);
        return VK_ERROR_OUT_OF_HOST_MEMORY;
    }
    const auto result = original<PFN_vkQueueSubmit>("vkQueueSubmit")(queue, count, submissions, fence);
    if (result == VK_SUCCESS) {
        std::lock_guard lock(tracking->mutex);
        std::erase(tracking->rejectedFences, fence);
        tracking->acceptedSubmissions.fetch_add(1);
    }
    return result;
}

PFN_vkVoidFunction VKAPI_CALL deviceProc(VkDevice device, const char* name) {
    if (std::strcmp(name, "vkDestroyFence") == 0) return reinterpret_cast<PFN_vkVoidFunction>(destroyFence);
    if (std::strcmp(name, "vkQueueSubmit") == 0) return reinterpret_cast<PFN_vkVoidFunction>(queueSubmit);
    if (std::strcmp(name, "vkDestroyBuffer") == 0) return reinterpret_cast<PFN_vkVoidFunction>(destroyBuffer);
    if (std::strcmp(name, "vkFreeMemory") == 0) return reinterpret_cast<PFN_vkVoidFunction>(freeMemory);
    if (std::strcmp(name, "vkAllocateMemory") == 0) return reinterpret_cast<PFN_vkVoidFunction>(allocateMemory);
    if (std::strcmp(name, "vkBindBufferMemory") == 0) return reinterpret_cast<PFN_vkVoidFunction>(bindBufferMemory);
    if (std::strcmp(name, "vkGetBufferDeviceAddressKHR") == 0 && tracking->failAddressLookup.exchange(false)) return nullptr;
    return tracking->resolve(device, name);
}

struct Fixture {
    Context context;
    Tracking calls;
    std::unique_ptr<Recorder> recorder;
    explicit Fixture(const Context& source) : context(source), calls{source.deviceProc, source.device} {
        Require(tracking == nullptr, "host import tracking is already active");
        tracking = &calls;
        context.deviceProc = deviceProc;
        context.functions = nullptr;
        std::lock_guard gpu(GpuMutex());
        recorder = std::make_unique<Recorder>(context);
        recorder->Activate();
    }
    ~Fixture() {
        std::lock_guard gpu(GpuMutex());
        recorder.reset();
        for (const auto fence : calls.rejectedFences) original<PFN_vkDestroyFence>("vkDestroyFence")(context.device, fence, nullptr);
        ClearHostImports(context.device);
        context.bufferPool.reset();
        tracking = nullptr;
    }
    std::shared_ptr<ImportState> Import(std::uint64_t address, std::size_t bytes) {
        std::lock_guard gpu(GpuMutex());
        const auto* imported = HostImportFor(context, address, bytes);
        Require(imported != nullptr, "host pointer import was refused for the lifetime test");
        const auto state = calls.Find(imported->memory);
        Require(state != nullptr && state->buffer == imported->buffer && state->address == address && state->bytes == bytes, "host import was not observed by the real allocation and bind callbacks");
        return state;
    }
    void Cleanup() {
        std::lock_guard gpu(GpuMutex());
        recorder->Sync();
        ClearHostImports(context.device);
    }
};

struct Allocation {
    Fixture& fixture;
    const std::size_t alignment;
    const std::size_t bytes;
    void* data;
    bool registered = true;
    bool released = false;
    bool completed = false;
    std::shared_ptr<ImportState> imported;
    std::unique_ptr<Buffer> result;
    Allocation(Fixture& fixture, std::size_t units = 1)
        : fixture(fixture), alignment(std::max<VkDeviceSize>(65536, fixture.context.hostImportAlignment)), bytes(alignment * units), data(::operator new(bytes, std::align_val_t{alignment})) {
        std::memset(data, 0x37, bytes);
        GuestAllocations::Mutation().Add(data, bytes, true, true, true);
    }
    ~Allocation() {
        fixture.Cleanup();
        if (registered) GuestAllocations::Mutation().Remove(data);
        Release();
    }
    std::uint64_t Address() const { return reinterpret_cast<std::uint64_t>(data); }
    auto Import() { return imported = fixture.Import(Address(), bytes); }
    bool Covered() const { return HostImportCovers(fixture.context, Address(), bytes); }
    void Release() {
        if (!released) ::operator delete(data, std::align_val_t{alignment});
        released = true;
    }
    void Remove() {
        GuestAllocations::Mutation().Remove(data);
        registered = false;
        imported->Verify();
    }
    void Unmap(const std::function<void()>& check = {}) {
        GuestAllocations::Mutation().Unmap(data, bytes, [&](const void*, std::size_t, const void*, bool) {
            imported->Verify();
            if (check) check();
            Release();
        });
        registered = false;
        Require(!Covered(), "an unmapped range still has a live host import");
    }
    void Permissions(GuestAllocations::Mutation& mutation, bool writable = true) const {
        const auto range = mutation.Find(data);
        Require(range.readable && range.writable == writable && range.gpu, "guest registration has unexpected permissions");
    }
    void Copy(bool keepLease = true) {
        std::lock_guard gpu(GpuMutex());
        completed = false;
        if (result == nullptr) result = std::make_unique<Buffer>(fixture.context, bytes, VK_BUFFER_USAGE_TRANSFER_DST_BIT);
        const auto commands = fixture.recorder->Commands();
        RecordMemoryBarrier(fixture.context, commands, VK_PIPELINE_STAGE_HOST_BIT, VK_PIPELINE_STAGE_TRANSFER_BIT, VK_ACCESS_HOST_WRITE_BIT, VK_ACCESS_TRANSFER_READ_BIT);
        CopyBuffer(fixture.context, commands, imported->buffer, 0, result->Handle(), 0, bytes);
        RecordMemoryBarrier(fixture.context, commands, VK_PIPELINE_STAGE_TRANSFER_BIT, VK_PIPELINE_STAGE_HOST_BIT, VK_ACCESS_TRANSFER_WRITE_BIT, VK_ACCESS_HOST_READ_BIT);
        fixture.recorder->NotePendingRead(Address(), bytes, Recorder::ReadKind::AddressBased);
        if (keepLease) fixture.recorder->Keep(std::make_shared<GuestAllocations::Lease>(GuestAllocations::GuestAllocationsAcquire_nid_postfix()));
        fixture.recorder->OnComplete([this] { completed = true; });
    }
    void VerifyCopy() {
        Require(completed, "guest mutation passed a pending GPU read");
        result->Invalidate();
        const auto copied = result->Bytes();
        Require(std::all_of(copied.begin(), copied.end(), [](std::byte value) { return value == std::byte{0x37}; }), "GPU read lost the source contents before guest unmap");
    }
};

void descriptorFirstImport(Fixture& fixture) {
    Require(fixture.calls.lastAllocated == nullptr, "descriptor-only lifetime test did not run before the first host import");
    Allocation allocation(fixture);
    {
        std::lock_guard gpu(GpuMutex());
        GuestBufferMemory memory(fixture.context);
        memory.AddReadable(allocation.Address(), allocation.bytes);
        memory.Upload(false);
        allocation.imported = fixture.calls.lastAllocated;
        Require(allocation.imported != nullptr && allocation.imported->address == allocation.Address(), "descriptor-only upload did not import its allocation");
        std::uint32_t adjustment = 0;
        const auto descriptor = memory.Descriptor(allocation.Address(), allocation.bytes, adjustment);
        Require(descriptor.buffer == allocation.imported->buffer && descriptor.offset == 0 && adjustment == 0, "descriptor-only upload did not bind the tracked import");
    }
    Require(allocation.Covered(), "descriptor-only import did not persist after its build ended");
    allocation.Unmap();
}

void idleUnmap(Fixture& fixture) {
    Allocation allocation(fixture);
    allocation.Import();
    allocation.Unmap();
}

void pendingRead(Fixture& fixture, bool submitted, bool locked) {
    Allocation allocation(fixture);
    allocation.Import();
    std::unique_lock gpu(GpuMutex());
    allocation.Copy();
    if (submitted) fixture.recorder->Submit();
    if (!locked) gpu.unlock();
    allocation.Unmap([&] { allocation.VerifyCopy(); });
}

void productionWaiterFailure(Fixture& fixture) {
    Allocation allocation(fixture);
    const auto imported = allocation.Import();
    allocation.Copy();
    const auto rejectedBefore = fixture.calls.rejectedSubmissions.load();
    const auto acceptedBefore = fixture.calls.acceptedSubmissions.load();
    fixture.calls.failQueueSubmit.store(true);
    bool applied = false;
    std::string error;
    {
        GuestAllocations::Mutation mutation;
        error = failure([&] { mutation.Protect(allocation.data, allocation.bytes, true, true, true, [&] { applied = true; }); });
        allocation.Permissions(mutation);
    }
    Require(!fixture.calls.failQueueSubmit.load() && fixture.calls.rejectedSubmissions.load() == rejectedBefore + 1, "production pin waiter did not reach the injected queue submission failure");
    Require(fixture.calls.acceptedSubmissions.load() == acceptedBefore, "failed production waiter accepted GPU work before reporting failure");
    Require(error == "AGC graphics: vkQueueSubmit recorder: Vulkan result -1" && !applied, "production pin waiter did not propagate the original Vulkan error before host apply");
    Require(!imported->destroyed.load() && imported->frees.load() == 0 && allocation.Covered(), "failed production waiter retired its host import");
    allocation.Copy();
    allocation.Unmap([&] { allocation.VerifyCopy(); });
    Require(fixture.calls.acceptedSubmissions.load() == acceptedBefore + 1, "production waiter retry did not submit exactly its new copy");
    imported->Verify();
}

void partialUnmap(Fixture& fixture) {
    Allocation allocation(fixture, 3), unrelated(fixture);
    const auto imported = allocation.Import();
    const auto other = unrelated.Import();
    auto* middle = static_cast<std::byte*>(allocation.data) + allocation.alignment;
    GuestAllocations::Mutation().Unmap(middle, allocation.alignment, [&](const void* piece, std::size_t bytes, const void* original, bool last) {
        imported->Verify();
        Require(other->frees.load() == 0, "partial unmap retired a disjoint host import");
        Require(piece == middle && bytes == allocation.alignment && original == allocation.data && !last, "partial unmap changed the wrong guest extent");
    });
    Require(!RegisteredReadableCovers(reinterpret_cast<std::uint64_t>(middle), allocation.alignment), "the middle of a partial unmap remains registered");
    const auto low = fixture.Import(allocation.Address(), allocation.alignment);
    const auto high = fixture.Import(allocation.Address() + 2 * allocation.alignment, allocation.alignment);
    Require(low->frees.load() == 0 && high->frees.load() == 0 && other->frees.load() == 0, "remaining partial mappings could not be imported");
    allocation.Remove();
    low->Verify();
    high->Verify();
    Require(other->frees.load() == 0, "removing a split allocation retired a disjoint import");
}

void protectRollback(Fixture& fixture) {
    Allocation allocation(fixture);
    allocation.Import();
    bool called = false;
    const auto error = failure([&] {
        GuestAllocations::Mutation().Protect(allocation.data, allocation.bytes, true, false, true, [&] {
            allocation.imported->Verify();
            called = true;
            throw std::runtime_error("expected host protection failure");
        });
    });
    Require(called && error == "expected host protection failure", "unexpected protection failure");
    {
        GuestAllocations::Mutation mutation;
        allocation.Permissions(mutation);
    }
    allocation.Import();
    GuestAllocations::Mutation().Protect(allocation.data, allocation.bytes, true, false, true, [&] { allocation.imported->Verify(); });
    {
        GuestAllocations::Mutation mutation;
        allocation.Permissions(mutation, false);
        mutation.Protect(allocation.data, allocation.bytes, true, true, true, [] {});
    }
    allocation.Import();
    allocation.Remove();
}

struct FreeGate {
    std::promise<void> release;
    std::future<void> entered;
    bool open = false;
    explicit FreeGate(ImportState& state) : entered(state.freeing.get_future()) { state.allowFree = release.get_future().share(); }
    ~FreeGate() { Open(); }
    void Open() {
        if (!open) release.set_value();
        open = true;
    }
};

void blockingFree(Fixture& fixture, bool deferred) {
    std::optional<Allocation> first;
    std::optional<GuestBufferMemory> build;
    if (deferred) {
        first.emplace(fixture);
        std::lock_guard gpu(GpuMutex());
        build.emplace(fixture.context);
        build->AcquireRegistered();
        build->UploadPrepare(true);
    }
    Allocation allocation(fixture);
    const auto imported = allocation.Import();
    std::optional<Allocation> generation;
    if (deferred) {
        std::lock_guard gpu(GpuMutex());
        allocation.Copy(false);
        fixture.recorder->Submit();
        Check(fixture.context.Function<PFN_vkQueueWaitIdle>("vkQueueWaitIdle")(fixture.context.queue), "vkQueueWaitIdle retirement fixture");
        generation.emplace(fixture);
        Require(!fixture.recorder->Idle(), "retirement fixture has no submitted batch");
    }
    FreeGate gate(*imported);
    if (deferred) {
        std::lock_guard gpu(GpuMutex());
        build->UploadFinish(true);
        Require(!allocation.Covered() && imported->frees.load() == 0, "retirement did not move its cached import into the pending batch");
        fixture.recorder->Sync();
    }
    const bool workerEntered = deferred && gate.entered.wait_for(std::chrono::seconds(2)) == std::future_status::ready;
    const bool onReleaseThread = workerEntered && imported->freeingThread != std::this_thread::get_id();
    std::atomic<bool> applied{false};
    const auto waitsBefore = LeaseCounters().contentionWaits;
    std::promise<void> starting;
    auto started = starting.get_future();
    auto mutation = std::async(std::launch::async, [&] {
        starting.set_value();
        allocation.Unmap([&] { applied.store(true); });
    });
    started.wait();
    const bool entered = deferred ? workerEntered : gate.entered.wait_for(std::chrono::seconds(2)) == std::future_status::ready;
    const auto deadline = std::chrono::steady_clock::now() + std::chrono::seconds(1);
    while (deferred && LeaseCounters().contentionWaits == waitsBefore && mutation.wait_for(std::chrono::milliseconds(0)) == std::future_status::timeout && std::chrono::steady_clock::now() < deadline) std::this_thread::yield();
    const bool reachedWaiter = !deferred || LeaseCounters().contentionWaits > waitsBefore;
    const bool blocked = mutation.wait_for(std::chrono::milliseconds(0)) == std::future_status::timeout;
    const bool premature = applied.load();
    const bool registered = RegisteredReadableCovers(allocation.Address(), allocation.bytes);
    gate.Open();
    mutation.get();
    Require(entered && (!deferred || onReleaseThread), "Vulkan import destruction did not reach the expected release thread");
    Require(reachedWaiter && blocked && !premature && registered, "guest mutation passed an import whose Vulkan free was still running");
    Require(applied.load(), "guest mutation did not resume after Vulkan free");
    imported->Verify();
    if (deferred) allocation.VerifyCopy();
}

void blockedFree(Fixture& fixture) { blockingFree(fixture, false); }
void deferredRetirement(Fixture& fixture) { blockingFree(fixture, true); }

void failedConstruction(Fixture& fixture) {
    Allocation allocation(fixture);
    fixture.calls.failAddressLookup.store(true);
    const auto error = failure([&] { allocation.Import(); });
    Require(error.find("vkGetBufferDeviceAddressKHR") != std::string::npos && !fixture.calls.failAddressLookup.load(), "import construction did not reach the injected Vulkan resolver failure");
    const auto allocated = fixture.calls.lastAllocated;
    Require(allocated != nullptr && allocated->address == allocation.Address(), "resolver failure happened before host memory was imported");
    if (allocated->frees.load() == 0) {
        destroyBuffer(fixture.context.device, allocated->buffer, nullptr);
        freeMemory(fixture.context.device, allocated->memory, nullptr);
        throw std::runtime_error("failed host import construction leaked its Vulkan memory");
    }
    allocated->Verify();
    Require(!allocation.Covered(), "failed host import construction remained cached");
    allocation.Import();
    allocation.Remove();
    Require(allocated->frees.load() == 1, "retry destroyed the failed import a second time");
}

void mutationDuringCompletion(Fixture& fixture) {
    bool rejected = false;
    bool applied = false;
    bool laterCompletion = false;
    Allocation allocation(fixture);
    const auto imported = allocation.Import();
    std::lock_guard gpu(GpuMutex());
    allocation.Copy(false);
    fixture.recorder->OnComplete([&] {
        const auto error = failure([&] { GuestAllocations::Mutation().Protect(allocation.data, allocation.bytes, false, false, false, [&] { applied = true; }); });
        rejected = error.find("active GPU completion") != std::string::npos;
    });
    fixture.recorder->OnComplete([&] {
        laterCompletion = true;
        allocation.VerifyCopy();
    });
    fixture.recorder->Sync();
    Require(rejected && !applied, "an active completion allowed guest memory mutation before later completions");
    Require(laterCompletion, "rejecting a completion mutation lost later GPU results");
    Require(imported->frees.load() == 0, "rejecting a completion mutation retired its host import");
    {
        GuestAllocations::Mutation mutation;
        allocation.Permissions(mutation);
    }
    allocation.Remove();
}

void completedLeaseUnderLock(Fixture& fixture) {
    Allocation allocation(fixture);
    allocation.Import();
    std::lock_guard gpu(GpuMutex());
    fixture.recorder->Keep(std::make_shared<GuestAllocations::Lease>(GuestAllocations::GuestAllocationsAcquire_nid_postfix()));
    fixture.recorder->Sync();
    Require(fixture.recorder->Idle(), "completed lease test recorder is not idle");
    allocation.Remove();
}

struct MutationRace {
    Fixture* fixture;
    Allocation* allocation;
    std::shared_ptr<ImportState> replacement;
    unsigned calls = 0;
};
MutationRace* mutationRace = nullptr;

bool raceWaiter(std::uintptr_t address, std::size_t bytes) {
    auto& race = *mutationRace;
    Require(address == race.allocation->Address() && bytes == race.allocation->bytes, "pin waiter received the wrong mutation extent");
    std::lock_guard gpu(GpuMutex());
    race.fixture->Cleanup();
    if (++race.calls == 1) race.replacement = race.fixture->Import(address, bytes);
    return true;
}

bool failingWaiter(std::uintptr_t, std::size_t) { throw std::runtime_error("expected pin waiter failure"); }

void waiterFailure(Fixture& fixture) {
    Allocation allocation(fixture);
    const auto imported = allocation.Import();
    GuestAllocations::GuestAllocationsSetPinWaiter_nid_postfix(&failingWaiter);
    bool failed = false;
    bool excluded = false;
    std::future<void> reader;
    {
        GuestAllocations::Mutation mutation;
        const auto error = failure([&] {
            mutation.Protect(allocation.data, allocation.bytes, false, false, false, [] { throw std::runtime_error("host apply ran after a pin waiter failure"); });
        });
        failed = error == "expected pin waiter failure";
        std::promise<void> starting;
        auto ready = starting.get_future();
        reader = std::async(std::launch::async, [&] {
            starting.set_value();
            static_cast<void>(GuestAllocations::GuestAllocationsAcquire_nid_postfix());
        });
        ready.wait();
        excluded = reader.wait_for(std::chrono::milliseconds(20)) == std::future_status::timeout;
        allocation.Permissions(mutation);
    }
    reader.get();
    Require(failed && excluded, "a pin waiter error did not propagate with the registry lock restored");
    Require(imported->frees.load() == 0, "a failed pin waiter retired an import");
}

void reimportBeforeRelock(Fixture& fixture) {
    Allocation allocation(fixture);
    allocation.Import();
    MutationRace race{&fixture, &allocation};
    mutationRace = &race;
    GuestAllocations::GuestAllocationsSetPinWaiter_nid_postfix(&raceWaiter);
    allocation.Unmap([&] {
        Require(race.calls == 2 && race.replacement != nullptr, "guest mutation did not recheck an import acquired before registry relock");
        race.replacement->Verify();
    });
    mutationRace = nullptr;
}

}

int RunHostImportLifetimeTests(const Context& context) {
    if (context.hostImportAlignment == 0) {
        std::puts("skipped, the device has no VK_EXT_external_memory_host");
        return 77;
    }
    Fixture fixture(context);
    descriptorFirstImport(fixture);
    idleUnmap(fixture);
    pendingRead(fixture, false, false);
    pendingRead(fixture, true, false);
    pendingRead(fixture, false, true);
    pendingRead(fixture, true, true);
    partialUnmap(fixture);
    protectRollback(fixture);
    completedLeaseUnderLock(fixture);
    mutationDuringCompletion(fixture);
    blockedFree(fixture);
    failedConstruction(fixture);
    productionWaiterFailure(fixture);
    deferredRetirement(fixture);
    std::puts("host import lifetime tests passed");
    return 0;
}

int RunHostImportMutationRaceTests(const Context& context) {
    if (context.hostImportAlignment == 0) {
        std::puts("skipped, the device has no VK_EXT_external_memory_host");
        return 77;
    }
    Fixture fixture(context);
    waiterFailure(fixture);
    reimportBeforeRelock(fixture);
    std::puts("host import mutation race tests passed");
    return 0;
}
