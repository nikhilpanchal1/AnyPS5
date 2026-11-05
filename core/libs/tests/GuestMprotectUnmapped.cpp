#include "prx/libkernel/include/Api.hpp"
#include "prx/libc/include/Api.hpp"
#include "prx/libc/include/general/VabiMacros.hpp"
#include "prx/libkernel/KernelErrors.hpp"
#include "prx/libkernel/DirectMemory/DirectMemory.hpp"
#include "SceTypes.hpp"
#include <cerrno>
#include <cstdint>
#include <cstdio>
#include <cstdlib>
#include <exception>
#include <limits>
#include <stdexcept>
#include <string_view>
#include <system_error>
#include <utility>
#include <vector>
#ifdef __linux__
#include "prx/libkernel/Pthread/include/Pthread.hpp"
#include <pthread.h>
#endif

namespace {

constexpr std::size_t Page = 0x4000;
constexpr int ProtectRead = 1;
constexpr int ProtectReadWrite = 3;

void Require(bool condition, const char* what) {
    if (condition) return;
    std::fprintf(stderr, "%s\n", what);
    std::abort();
}

int Protect(const void* address, std::size_t bytes, int protection) {
    try {
        return sceKernelMprotect(address, bytes, protection);
    } catch (const std::exception& error) {
        std::fprintf(stderr, "sceKernelMprotect threw: %s\n", error.what());
        std::abort();
    }
}

int ProtectionAt(const unsigned char* address) {
    VirtualQueryInfo info{};
    Require(sceKernelVirtualQuery(address, 0, &info, sizeof(info)) == 0, "virtual query of a mapped page failed");
    return info.protection;
}

unsigned char* Map(std::size_t pages) {
    void* raw = mmap_nid_postfix(nullptr, Page * pages, ProtectReadWrite, 0x1002, -1, 0);
    Require(raw != reinterpret_cast<void*>(static_cast<std::uintptr_t>(-1)), "mmap failed");
    return static_cast<unsigned char*>(raw);
}

}

namespace MtypeprotectFlexible {

constexpr std::size_t Page = 0x4000;

void Require(bool condition, const char* reason) {
    if (!condition) throw std::runtime_error(reason);
}

enum class InitialMapping { Reservation, Flexible };

class Layout final {
    void* base = nullptr;
    std::size_t pages;
    std::vector<std::pair<std::int64_t, std::size_t>> allocations;

public:
    explicit Layout(std::size_t count, InitialMapping mapping = InitialMapping::Reservation) : pages(count) {
        if (mapping == InitialMapping::Flexible)
            Require(sceKernelMapFlexibleMemory(&base, Page * pages, 3, 0) == 0 && base != nullptr, "map fresh non-fixed flexible memory failed");
        else
            Require(sceKernelReserveVirtualRange(&base, Page * pages, 0, 0) == 0, "reserve virtual range failed");
    }

    ~Layout() {
        try {
            Require(sceKernelMunmap(reinterpret_cast<std::uint64_t>(base), Page * pages) == 0, "unmap layout failed");
            for (const auto& [physical, bytes] : allocations)
                Require(sceKernelReleaseDirectMemory(physical, bytes) == 0, "release direct allocation failed");
        } catch (const std::exception& error) {
            std::fprintf(stderr, "cleanup: %s\n", error.what());
            std::abort();
        }
    }

    Layout(const Layout&) = delete;
    Layout& operator=(const Layout&) = delete;

    unsigned char* At(std::size_t index) const {
        return static_cast<unsigned char*>(base) + Page * index;
    }

    std::int64_t Allocate(std::size_t count = 1) {
        std::int64_t physical = -1;
        const auto bytes = count * Page;
        Require(sceKernelAllocateDirectMemory(0, std::numeric_limits<std::int64_t>::max(), bytes, 0, 0, &physical) == 0, "allocate direct memory failed");
        allocations.emplace_back(physical, bytes);
        return physical;
    }

    std::int64_t Direct(std::size_t index, std::size_t count = 1) {
        const auto physical = Allocate(count);
        void* address = At(index);
        Require(sceKernelMapDirectMemory(&address, count * Page, 3, 0x10, physical, 0) == 0 && address == At(index), "map fixed direct memory failed");
        return physical;
    }

    void Alias(std::size_t index, std::int64_t physical) const {
        void* address = At(index);
        Require(sceKernelMapDirectMemory(&address, Page, 3, 0x10, physical, 0) == 0 && address == At(index), "map fixed direct alias failed");
    }

    void Flexible(std::size_t index, std::size_t count = 1, int kind = 0) {
        void* address = At(index);
        int result;
        if (kind == 1) result = sceKernelMapNamedFlexibleMemory(&address, Page * count, 3, 0x10, "mtypeprotect");
        else if (kind == 2) result = sceKernelMapNamedFlexibleMemoryInternal(&address, Page * count, 3, 0x10, "mtypeprotect");
        else result = sceKernelMapFlexibleMemory(&address, Page * count, 3, 0x10);
        Require(result == 0 && address == At(index), "map fixed flexible memory failed");
    }

    void Unmap(std::size_t index, std::size_t count = 1) const {
        Require(sceKernelMunmap(reinterpret_cast<std::uint64_t>(At(index)), Page * count) == 0, "unmap pages failed");
    }

    void Reject(std::size_t index, std::size_t count, int type = 3, int protection = 1) const {
        RejectBytes(At(index), Page * count, type, protection);
    }

    void RejectBytes(const void* address, std::size_t bytes, int type = 3, int protection = 1) const {
        bool refused = false;
        try {
            const int result = sceKernelMtypeprotect(address, bytes, type, protection);
            std::fprintf(stderr, "explicit flexible mtypeprotect returned 0x%08x instead of throwing\n", static_cast<unsigned>(result));
        } catch (const std::runtime_error& error) {
            if (std::string_view(error.what()) != "sceKernelMtypeprotect not implemented") throw;
            refused = true;
        }
        Require(refused, "mtypeprotect did not refuse an explicit flexible range");
    }

    void Check(std::size_t index, bool direct, int protection, int type = 0) const {
        VirtualQueryInfo info{};
        Require(sceKernelVirtualQuery(At(index), 0, &info, sizeof(info)) == 0, "query mapped page failed");
        Require(static_cast<bool>(info.is_direct) == direct, "mapping kind changed");
        Require(info.protection == protection, "page protection changed unexpectedly");
        if (direct) Require(info.memory_type == type, "direct mapping type changed unexpectedly");
    }
};

void CheckPhysical(std::int64_t physical, int expected) {
    int type = -1;
    std::int64_t start = -1;
    std::int64_t end = -1;
    Require(DirectMemoryFind(physical, false, &start, &end, &type), "query physical type failed");
    Require(type == expected, "physical allocation type changed unexpectedly");
}

void CheckRefusalContents(const Layout& layout, std::size_t directIndex, std::size_t flexibleIndex, std::size_t aliasIndex) {
    volatile unsigned char* direct = layout.At(directIndex);
    volatile unsigned char* flexible = layout.At(flexibleIndex);
    volatile unsigned char* alias = layout.At(aliasIndex);
    for (const auto offset : {std::size_t{0}, Page - 1}) {
        Require(direct[offset] == 41 && flexible[offset] == 77 && alias[offset] == 41, "refusal changed mapped contents or direct alias backing");
        direct[offset] = 42;
        Require(alias[offset] == 42, "direct write no longer reaches its alias");
        alias[offset] = 43;
        flexible[offset] = 78;
        Require(direct[offset] == 43 && flexible[offset] == 78, "refused memory lost native read/write access or alias identity");
        alias[offset] = 41;
        flexible[offset] = 77;
    }
}

void MixedRangeRefusal() {
    Layout layout(3);
    const auto physical = layout.Direct(0);
    layout.Flexible(1);
    layout.Alias(2, physical);
    for (const auto offset : {std::size_t{0}, Page - 1}) {
        layout.At(0)[offset] = 41;
        layout.At(1)[offset] = 77;
    }
    layout.Check(0, true, 3);
    layout.Check(1, false, 3);
    for (int type : {3, 0, -1, std::numeric_limits<int>::min(), std::numeric_limits<int>::max()}) {
        for (int protection : {1, 3, 2, 0x20, 0x32, 0xf2}) {
            layout.Reject(0, 2, type, protection);
            layout.Check(0, true, 3);
            layout.Check(1, false, 3);
            layout.Check(2, true, 3);
            CheckPhysical(physical, 0);
            CheckRefusalContents(layout, 0, 1, 2);
        }
    }
}

void FlexibleFirst() {
    Layout layout(3);
    layout.Flexible(0);
    const auto physical = layout.Direct(1);
    layout.Alias(2, physical);
    for (const auto offset : {std::size_t{0}, Page - 1}) {
        layout.At(1)[offset] = 41;
        layout.At(0)[offset] = 77;
    }
    layout.Reject(0, 2);
    layout.Check(0, false, 3);
    layout.Check(1, true, 3);
    layout.Check(2, true, 3);
    CheckPhysical(physical, 0);
    CheckRefusalContents(layout, 1, 0, 2);
}

void FlexibleMaps() {
    for (int kind = 0; kind < 3; ++kind) {
        Layout layout(3);
        layout.Flexible(0, 3, kind);
        Require(sceKernelMtypeprotect(layout.At(1), 0, 3, 1) == 0, "zero-length mtypeprotect failed");
        layout.Reject(1, 1);
        for (std::size_t page = 0; page < 3; ++page) layout.Check(page, false, 3);
    }
}

void FreshFlexibleMapping() {
    Layout layout(3, InitialMapping::Flexible);
    for (std::size_t page = 0; page < 3; ++page) layout.At(page)[0] = static_cast<unsigned char>(31 + page);
    layout.Reject(1, 1);
    for (std::size_t page = 0; page < 3; ++page) {
        layout.Check(page, false, 3);
        Require(layout.At(page)[0] == 31 + page, "fresh flexible mapping contents changed after refusal");
    }
}

void AliasedFlexibleOutput() {
    Layout layout(3);
    layout.Flexible(0, 3);
    layout.At(0)[0] = 71;
    layout.At(2)[0] = 73;
    auto* const target = layout.At(1);
    auto* const cell = target + 64;
    *reinterpret_cast<void**>(cell) = target;
    Require(sceKernelMapFlexibleMemory(reinterpret_cast<void**>(cell), Page, 3, 0x10) == 0, "flexible remap with an aliased output pointer failed");
    VirtualQueryInfo info{};
    Require(sceKernelVirtualQuery(target, 0, &info, sizeof(info)) == 0 && !info.is_direct && info.protection == 3,
            "actual aliased-output remap target was not mapped read/write");
    target[0] = 72;
    layout.RejectBytes(target, Page);
    layout.Reject(0, 3);
    for (std::size_t page = 0; page < 3; ++page) {
        layout.Check(page, false, 3);
        Require(layout.At(page)[0] == 71 + page, "aliased-output remap refusal changed contents");
    }
}

void ProtectionChangesPreserveIdentity() {
    Layout layout(2);
    const auto physical = layout.Direct(0);
    layout.Flexible(1);
    layout.At(1)[0] = 47;
    for (bool posix : {false, true}) {
        const int protection = posix ? 3 : 1;
        const int result = posix ? mprotect_nid_postfix(layout.At(1), Page, protection)
                                 : sceKernelMprotect(layout.At(1), Page, protection);
        Require(result == 0, "ordinary flexible protection change failed");
        layout.Check(1, false, protection);
        layout.Reject(0, 2, 3, posix ? 1 : 3);
        layout.Check(0, true, 3);
        layout.Check(1, false, protection);
        CheckPhysical(physical, 0);
        Require(layout.At(1)[0] == 47, "flexible contents changed after ordinary protection and refusal");
    }
    layout.At(1)[0] = 48;
    Require(layout.At(1)[0] == 48, "restored flexible mapping is not writable");
}

void MixedGaps() {
    Layout layout(5);
    const auto first = layout.Direct(0);
    layout.Flexible(2);
    const auto last = layout.Direct(4);
    layout.Unmap(1);
    layout.Unmap(3);
    layout.Reject(0, 5);
    layout.Reject(1, 4);
    layout.Check(0, true, 3);
    layout.Check(2, false, 3);
    layout.Check(4, true, 3);
    CheckPhysical(first, 0);
    CheckPhysical(last, 0);
}

void PartialUnmap() {
    Layout layout(4);
    layout.Flexible(0, 4);
    layout.Unmap(1, 2);
    layout.Reject(0, 4);
    layout.Reject(0, 1);
    layout.Reject(3, 1);
    layout.Check(0, false, 3);
    layout.Check(3, false, 3);
    Require(sceKernelMtypeprotect(layout.At(1), Page * 2, 3, 1) == 0, "unmapped former flexible pages were rejected");
    const auto physical = layout.Direct(1, 2);
    Require(sceKernelMtypeprotect(layout.At(1), Page * 2, 3, 1) == 0, "direct pages between flexible neighbors were rejected");
    layout.Check(1, true, 1, 3);
    layout.Check(2, true, 1, 3);
    CheckPhysical(physical, 3);
    layout.Reject(0, 4);
    layout.Check(1, true, 1, 3);
    layout.Check(2, true, 1, 3);
    layout.Unmap(0);
    layout.Unmap(3);
    Require(sceKernelMtypeprotect(layout.At(0), Page * 4, 5, 3) == 0, "removed flexible pages still reject a mixed range");
    layout.Check(1, true, 3, 5);
    layout.Check(2, true, 3, 5);
    CheckPhysical(physical, 5);
}

#if defined(__linux__) || defined(__APPLE__)
void FailedHostUnmap() {
    Layout layout(4);
    const auto physical = layout.Direct(0);
    layout.Flexible(1, 3);
    for (std::size_t page = 1; page < 4; ++page) layout.At(page)[0] = static_cast<unsigned char>(59 + page);
    bool failed = false;
    try {
        sceKernelMunmap(reinterpret_cast<std::uint64_t>(layout.At(1) + 1), Page * 2);
    } catch (const std::system_error& error) {
        Require(error.code().value() == EINVAL, "unaligned host unmap failed for an unexpected reason");
        failed = true;
    }
    Require(failed, "unaligned host unmap did not fail");
    Require(layout.At(2)[0] == 61, "failed host unmap changed the original middle page");
    layout.Check(0, true, 3);
    for (std::size_t page = 1; page < 4; ++page) layout.Check(page, false, 3);
    CheckPhysical(physical, 0);
    layout.Reject(2, 1);
    layout.Reject(0, 4);
    layout.Check(0, true, 3);
    for (std::size_t page = 1; page < 4; ++page) {
        layout.Check(page, false, 3);
        Require(layout.At(page)[0] == 59 + page, "failed host unmap or subsequent refusal changed contents");
    }
    CheckPhysical(physical, 0);
}
#endif

void FixedReplacement() {
    Layout layout(3);
    layout.Flexible(0, 3);
    const auto middle = layout.Direct(1);
    Require(sceKernelMtypeprotect(layout.At(1), Page, 3, 1) == 0, "replacement direct page retained flexible classification");
    layout.Reject(0, 3);
    layout.Check(0, false, 3);
    layout.Check(1, true, 1, 3);
    layout.Check(2, false, 3);
    CheckPhysical(middle, 3);
    const auto first = layout.Direct(0);
    const auto last = layout.Direct(2);
    Require(sceKernelMtypeprotect(layout.At(0), Page * 3, 5, 1) == 0, "fully replaced flexible range was rejected");
    for (std::size_t page = 0; page < 3; ++page) layout.Check(page, true, 1, 5);
    for (const auto physical : {first, middle, last}) CheckPhysical(physical, 5);
}

void DirectAndUnmappedControls() {
    Layout layout(3);
    const auto physical = layout.Direct(0, 3);
    layout.Unmap(1);
    Require(sceKernelMtypeprotect(layout.At(0), Page * 3, 3, 1) == 0, "direct-only mtypeprotect with a gap failed");
    layout.Check(0, true, 1, 3);
    layout.Check(2, true, 1, 3);
    CheckPhysical(physical, 3);
    CheckPhysical(physical + Page, 0);
    CheckPhysical(physical + Page * 2, 3);
    layout.Unmap(0, 3);
    Require(sceKernelMtypeprotect(layout.At(0), Page * 3, 5, 3) == 0, "fully unmapped mtypeprotect failed");
    CheckPhysical(physical, 3);
    CheckPhysical(physical + Page, 0);
    CheckPhysical(physical + Page * 2, 3);
}

void ProtectionBoundaries() {
    Layout layout(2);
    const auto physical = layout.Direct(0);
    layout.Flexible(1);
    for (unsigned bit = 0; bit < 32; ++bit) {
        const auto flag = std::uint32_t{1} << bit;
        if ((flag & 0x3f7u) != 0) continue;
        layout.Reject(0, 2, 3, static_cast<int>(flag | 1u));
        layout.Check(0, true, 3);
        layout.Check(1, false, 3);
        CheckPhysical(physical, 0);
    }
    for (int protection : {4, 5, 0x100, 0x200, 0x300, 0x304, 0x3f7}) {
        layout.Reject(0, 2, 3, protection);
        layout.Check(0, true, 3);
        layout.Check(1, false, 3);
        CheckPhysical(physical, 0);
    }
}

void UnalignedBoundaries() {
    Layout layout(3);
    const auto first = layout.Direct(0);
    layout.Flexible(1);
    const auto last = layout.Direct(2);
    layout.RejectBytes(layout.At(1) + 13, 1);
    layout.RejectBytes(layout.At(1) - 1, 2);
    layout.RejectBytes(layout.At(2) - 1, 2);
    layout.Check(0, true, 3);
    layout.Check(1, false, 3);
    layout.Check(2, true, 3);
    CheckPhysical(first, 0);
    CheckPhysical(last, 0);
    Require(sceKernelMtypeprotect(layout.At(1) - 1, 1, 5, 1) == 0, "a range ending before flexible memory was rejected");
    Require(sceKernelMtypeprotect(layout.At(2), 1, 5, 1) == 0, "a range starting after flexible memory was rejected");
    layout.Check(0, true, 1, 5);
    layout.Check(1, false, 3);
    layout.Check(2, true, 1, 5);
    CheckPhysical(first, 5);
    CheckPhysical(last, 5);
}

void ReleasedMappingBoundary() {
    Layout layout(4);
    const auto physical = layout.Direct(0);
    layout.Flexible(1, 3);
    Require(sceKernelReleaseFlexibleMemory(layout.At(2), Page) == 0, "partial flexible budget release failed");
    layout.Reject(1, 1);
    layout.Reject(3, 1);
    layout.Reject(2, 1);
    layout.Reject(0, 4);
    layout.Check(0, true, 3);
    for (std::size_t page = 1; page < 4; ++page) layout.Check(page, false, 3);
    CheckPhysical(physical, 0);
    layout.Unmap(2);
    layout.Flexible(2);
    layout.Reject(0, 4);
    Require(sceKernelReleaseFlexibleMemory(layout.At(1), Page * 3) == 0, "full flexible budget release failed");
    layout.Reject(0, 4);
    layout.Check(0, true, 3);
    for (std::size_t page = 1; page < 4; ++page) layout.Check(page, false, 3);
    CheckPhysical(physical, 0);
}

void FailedReplacement() {
    Layout layout(3);
    layout.Flexible(0, 3);
    const auto physical = layout.Allocate();
    void* address = layout.At(1);
    Require(sceKernelMapDirectMemory(&address, Page, 3, 0x90, physical, 0) == SCE_KERNEL_ERROR_ENOMEM && address == layout.At(1), "NOOVERWRITE direct replacement was accepted");
    layout.Reject(0, 3);
    for (std::size_t page = 0; page < 3; ++page) layout.Check(page, false, 3);
    CheckPhysical(physical, 0);
}

void AnonymousReplacement() {
    Layout layout(3);
    layout.Flexible(0, 3);
    for (std::size_t page = 0; page < 3; ++page) layout.At(page)[0] = static_cast<unsigned char>(17 + page);
    Require(mmap_nid_postfix(layout.At(1), Page, 3, 0x1012, -1, 0) == layout.At(1), "fixed POSIX anonymous replacement failed");
    Require(layout.At(0)[0] == 17 && layout.At(1)[0] == 0 && layout.At(2)[0] == 19, "anonymous replacement changed the wrong contents");
    Require(sceKernelMtypeprotect(layout.At(1), Page, 3, 1) == 0, "anonymous replacement retained explicit flexible identity");
    layout.Reject(0, 3);
    layout.Check(0, false, 3);
    layout.Check(1, false, 1);
    layout.Check(2, false, 3);
    for (std::size_t page : {std::size_t{0}, std::size_t{2}})
        Require(mmap_nid_postfix(layout.At(page), Page, 3, 0x1012, -1, 0) == layout.At(page), "fixed POSIX anonymous edge replacement failed");
    Require(sceKernelMtypeprotect(layout.At(0), Page * 3, 3, 1) == 0, "fully replaced anonymous range retained explicit flexible identity");
    for (std::size_t page = 0; page < 3; ++page) layout.Check(page, false, 1);
}

void ReservationReplacement() {
    Layout layout(4);
    layout.Flexible(0, 4);
    void* address = layout.At(1);
    Require(sceKernelReserveVirtualRange(&address, Page * 2, 0x10, 0) == 0 && address == layout.At(1), "fixed reservation replacement failed");
    Require(sceKernelMtypeprotect(layout.At(1), Page * 2, 3, 1) == 0, "reservation replacement retained flexible identity");
    layout.Reject(0, 4);
    layout.Check(0, false, 3);
    layout.Check(3, false, 3);
}

#ifdef __linux__
struct FlexibleStackResult {
    void* address;
    bool recognized = false;
    bool refused = false;
    int query = -1;
    int restore = -1;
    VirtualQueryInfo after{};
    std::exception_ptr error;
};

void* FlexibleStackWorker(void* argument) noexcept {
    auto& state = *static_cast<FlexibleStackResult*>(argument);
    try {
        std::uintptr_t low = 0;
        std::uintptr_t high = 0;
        const auto address = reinterpret_cast<std::uintptr_t>(state.address);
        state.recognized = GuestThreadStack(address, &low, &high) && address >= low && address + Page <= high;
        try {
            sceKernelMtypeprotect(state.address, Page, 3, 1);
        } catch (const std::runtime_error& error) {
            if (std::string_view(error.what()) != "sceKernelMtypeprotect not implemented") throw;
            state.refused = true;
        }
        state.query = sceKernelVirtualQuery(state.address, 0, &state.after, sizeof(state.after));
    } catch (...) {
        state.error = std::current_exception();
    }
    try {
        state.restore = sceKernelMprotect(state.address, Page, 3);
    } catch (...) {
        if (!state.error) state.error = std::current_exception();
    }
    return nullptr;
}

void FlexibleStack() {
    constexpr std::size_t pages = 128;
    Layout layout(pages);
    layout.Flexible(0, pages);
    pthread_attr_t attribute;
    Require(pthread_attr_init(&attribute) == 0, "initialize native stack attributes failed");
    const int guard = pthread_attr_setguardsize(&attribute, 0);
    const int stack = pthread_attr_setstack(&attribute, layout.At(0), Page * pages);
    if (guard != 0 || stack != 0) {
        pthread_attr_destroy(&attribute);
        throw std::runtime_error("configure native flexible stack failed");
    }
    FlexibleStackResult result{layout.At(1), false, false, -1, -1, {}, {}};
    pthread_t worker;
    const int created = pthread_create(&worker, &attribute, FlexibleStackWorker, &result);
    const int destroyed = pthread_attr_destroy(&attribute);
    Require(created == 0, "start native flexible-stack worker failed");
    Require(pthread_join(worker, nullptr) == 0, "join native flexible-stack worker failed");
    Require(destroyed == 0, "destroy native stack attributes failed");
    if (result.error) std::rethrow_exception(result.error);
    Require(result.recognized, "flexible stack did not reach real stack recognition");
    Require(result.refused, "stack protection shortcut bypassed explicit flexible refusal");
    Require(result.query == 0 && result.after.protection == 3, "refused flexible-stack operation changed protection");
    Require(result.restore == 0, "restore flexible-stack protection failed");
    layout.Check(1, false, 3);
}
#endif

void Run() {
    MixedRangeRefusal();
    FlexibleFirst();
    FlexibleMaps();
    FreshFlexibleMapping();
    AliasedFlexibleOutput();
    ProtectionChangesPreserveIdentity();
    MixedGaps();
    PartialUnmap();
#if defined(__linux__) || defined(__APPLE__)
    FailedHostUnmap();
#endif
    FixedReplacement();
    DirectAndUnmappedControls();
    ProtectionBoundaries();
    UnalignedBoundaries();
    ReleasedMappingBoundary();
    FailedReplacement();
    AnonymousReplacement();
    ReservationReplacement();
#ifdef __linux__
    FlexibleStack();
#endif
    std::puts("mtypeprotect explicit flexible refusal and lifecycle controls passed");
}

int RunChecked() {
    try {
        Run();
        return 0;
    } catch (const std::exception& error) {
        std::fprintf(stderr, "mtypeprotect flexible regression: %s\n", error.what());
        return 1;
    }
}

}

int main(int argc, char** argv) {
    if (argc == 2 && std::string_view(argv[1]) == "flexible") return MtypeprotectFlexible::RunChecked();
    unsigned char* memory = Map(3);
    Require(munmap_nid_postfix(memory + Page, Page) == 0, "munmap of the middle page failed");

    Require(Protect(memory, 0, ProtectRead) == 0, "a zero-length protection of a mapped page must succeed");
    Require(ProtectionAt(memory) == ProtectReadWrite, "a zero-length protection must not change the page");
    Require(Protect(memory + Page, 0, ProtectRead) == 0 && Protect(nullptr, 0, ProtectRead) == 0, "a zero-length protection of unmapped memory must succeed");
    Require(sceKernelMtypeprotect(memory, 0, 0, ProtectRead) == 0 && ProtectionAt(memory) == ProtectReadWrite, "a zero-length sceKernelMtypeprotect must succeed without changing the page");
    Require(mprotect_nid_postfix(memory + Page, 0, ProtectRead) == 0, "a zero-length mprotect of unmapped memory must succeed");

    Require(Protect(memory, Page * 3, ProtectRead) == 0, "a range with a gap in the middle must succeed for its mapped parts");
    Require(ProtectionAt(memory) == ProtectRead && ProtectionAt(memory + Page * 2) == ProtectRead, "the mapped parts on both sides of the gap must be protected");
    Require(mprotect_nid_postfix(memory, Page * 3, ProtectReadWrite) == 0, "mprotect over a range with a gap must succeed for its mapped parts");
    Require(ProtectionAt(memory) == ProtectReadWrite && ProtectionAt(memory + Page * 2) == ProtectReadWrite, "mprotect must change the mapped parts on both sides of the gap");
    Require(sceKernelMtypeprotect(memory, Page * 3, 0, ProtectRead) == 0, "sceKernelMtypeprotect over a range with a gap must succeed for its mapped parts");

    Require(Protect(memory + Page - 8, 16, ProtectReadWrite) == 0, "an unaligned range that reaches into the unmapped page protects the mapped page");
    Require(Protect(memory + 100, Page - 200, ProtectReadWrite) == 0, "an unaligned range inside the first page must work");

    Require(Protect(memory + Page, Page, ProtectRead) == 0, "a range that is completely unmapped must succeed");
    Require(Protect(memory + Page * 2, Page, ProtectReadWrite) == 0, "protecting the last page alone must work");
    Require(Protect(memory + Page, Page * 2, ProtectRead) == 0, "a range whose start is unmapped must succeed for the mapped pages behind it");
    Require(ProtectionAt(memory + Page * 2) == ProtectRead, "the mapped pages behind an unmapped start must be protected");
    Require(ProtectionAt(memory) == ProtectReadWrite, "a range that starts in a gap must not change the page before it");
    Require(mprotect_nid_postfix(memory + Page, Page, ProtectRead) == 0, "mprotect over a range that is completely unmapped must succeed");
    Require(mprotect_nid_postfix(memory + Page, Page * 2, ProtectReadWrite) == 0 && ProtectionAt(memory + Page * 2) == ProtectReadWrite, "mprotect over an unmapped start must protect the mapped pages behind it");
    Require(sceKernelMtypeprotect(memory + Page, Page, 0, ProtectRead) == 0, "sceKernelMtypeprotect over a range that is completely unmapped must succeed");

    Require(munmap_nid_postfix(memory, Page) == 0 && munmap_nid_postfix(memory + Page * 2, Page) == 0, "munmap of the remaining pages failed");

    unsigned char* tail = Map(2);
    Require(munmap_nid_postfix(tail + Page, Page) == 0, "munmap of the last page failed");
    Require(Protect(tail, Page * 2, ProtectRead) == 0, "a range that ends in an unmapped page must succeed for its mapped part");
    Require(ProtectionAt(tail) == ProtectRead, "the mapped part before a trailing gap must be protected");
    Require(munmap_nid_postfix(tail, Page) == 0, "munmap of the remaining page failed");
    Require(Protect(tail, Page * 2, ProtectRead) == 0, "a range over pages that were all unmapped must succeed");

    std::int64_t physical = -1;
    Require(sceKernelAllocateDirectMemory(0, std::numeric_limits<std::int64_t>::max(), Page * 3, 0, 0, &physical) == 0, "direct memory allocation failed");
    void* direct = nullptr;
    Require(sceKernelMapDirectMemory(&direct, Page * 3, ProtectReadWrite, 0, physical, 0) == 0, "direct memory map failed");
    auto* directPages = static_cast<unsigned char*>(direct);
    Require(munmap_nid_postfix(directPages, Page) == 0, "munmap of the first direct page failed");
    Require(sceKernelMtypeprotect(directPages, Page * 3, 3, ProtectRead) == 0, "sceKernelMtypeprotect over an unmapped start must succeed for the mapped direct pages");
    Require(ProtectionAt(directPages + Page) == ProtectRead && ProtectionAt(directPages + Page * 2) == ProtectRead, "the mapped direct pages behind an unmapped start must be protected");
    for (int page = 0; page < 3; ++page) {
        int type = -1;
        std::int64_t start = 0;
        std::int64_t end = 0;
        Require(sceKernelGetDirectMemoryType(physical + page * static_cast<std::int64_t>(Page), &type, &start, &end) == 0, "direct memory type query failed");
        Require(type == (page == 0 ? 0 : 3), "only the mapped direct pages must take the new memory type");
    }
    Require(munmap_nid_postfix(directPages + Page, Page * 2) == 0, "munmap of the direct pages failed");
    Require(sceKernelReleaseDirectMemory(physical, Page * 3) == 0, "direct memory release failed");
    return MtypeprotectFlexible::RunChecked();
}
