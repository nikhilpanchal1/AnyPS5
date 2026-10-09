#include "RecorderDevice.hpp"
#include "StorageEdgeWriteWatch.hpp"
#include "prx/libSceAgcDriver/Graphics/include/GuestBufferMemory.hpp"
#include "prx/libSceAgcDriver/Graphics/include/Recorder.hpp"
#include "prx/libSceAgcDriver/Graphics/include/Texture.hpp"
#include "prx/libSceAgcDriver/Graphics/include/TextureDetiler.hpp"
#include "prx/libSceAgcDriver/Execution/include/GuestMemory.hpp"
#include "prx/libc/include/GuestAllocations.hpp"
#include "prx/libc/include/GuestArena.hpp"
#include "prx/libc/include/GuestWriteWatch.hpp"
#include <algorithm>
#include <array>
#include <cstddef>
#include <cstdint>
#include <cstdlib>
#include <cstring>
#include <exception>
#include <iostream>
#include <limits>
#include <map>
#include <memory>
#include <mutex>
#include <string>
#include <vector>
#ifdef _WIN32
#ifndef NOMINMAX
#define NOMINMAX
#endif
#include <windows.h>
#else
#include <sys/mman.h>
#endif

namespace {

using namespace AgcDriver::Graphics;
namespace Memory = AgcDriver::GuestMemory;
constexpr std::size_t UnitBytes = 65536;
constexpr std::byte Initial{0xcd};
constexpr std::byte Neighbour{0x19};

void noteWrite(std::uintptr_t address, std::size_t bytes) {
#ifdef ANYPS5_TEST_WRITE_WATCH
    StorageEdgeNoteCpuWrite(address, bytes);
#else
    static_cast<void>(address);
    static_cast<void>(bytes);
#endif
}

class Surface {
public:
    Surface(const Context& baseContext, Recorder& recorder, std::size_t offset, std::uint32_t width = 512, std::uint32_t height = 512, bool queuedUpload = false, bool forceCpuFallback = false, bool defer = false) : context(baseContext), recorder(recorder), offset(offset) {
        if (forceCpuFallback) context.hostImportAlignment = 0;
        descriptor.width = width;
        descriptor.height = height;
        descriptor.mipCount = 1;
        descriptor.tileMode = TextureTileMode::kStandard4KB;
        descriptor.dimension = TextureDimension::k2D;
        descriptor.format = 1;
        descriptor.dstSelX = 4;
        descriptor.dstSelY = 0;
        descriptor.dstSelZ = 0;
        descriptor.dstSelW = 1;
        surfaceBytes = static_cast<std::size_t>(DescribeSurface(descriptor).guestBytes);
        allocationBytes = (offset + surfaceBytes + UnitBytes - 1) / UnitBytes * UnitBytes + UnitBytes;
#ifdef _WIN32
        allocation = GuestArena::GuestArenaAllocate_nid_postfix(allocationBytes, UnitBytes);
        GuestArena::GuestArenaCommit_nid_postfix(allocation, allocationBytes, PAGE_READWRITE, allocationBytes);
#else
        void* raw = mmap(nullptr, allocationBytes + UnitBytes, PROT_READ | PROT_WRITE, MAP_PRIVATE | MAP_ANONYMOUS, -1, 0);
        Require(raw != MAP_FAILED, "cannot allocate edge storage memory");
        const auto begin = reinterpret_cast<std::uintptr_t>(raw);
        const auto aligned = (begin + UnitBytes - 1) & ~(static_cast<std::uintptr_t>(UnitBytes) - 1);
        if (aligned != begin) munmap(raw, aligned - begin);
        if (aligned + allocationBytes != begin + allocationBytes + UnitBytes) munmap(reinterpret_cast<void*>(aligned + allocationBytes), begin + UnitBytes - aligned);
        allocation = reinterpret_cast<void*>(aligned);
        GuestWriteWatch::GuestWriteWatchRegister_nid_postfix(allocation, allocationBytes);
#endif
        Require(allocation != nullptr, "cannot allocate edge storage memory");
        const auto base = reinterpret_cast<std::uintptr_t>(allocation);
        descriptor.baseAddress = base + offset;
        std::memset(allocation, std::to_integer<int>(Neighbour), allocationBytes);
        std::memset(reinterpret_cast<void*>(descriptor.baseAddress), std::to_integer<int>(Initial), surfaceBytes);
        noteWrite(base, allocationBytes);
        {
            GuestAllocations::Mutation mutation;
            mutation.Add(allocation, allocationBytes, true, true);
        }
        const auto* hostImport = HostImportFor(context, base, allocationBytes);
        Require(forceCpuFallback ? hostImport == nullptr : hostImport != nullptr, "edge test did not select the expected upload path");
        Require(Memory::Watched(base, allocationBytes), "edge test memory is not write watched");
        if (queuedUpload) {
            const auto* import = HostImportFor(context, descriptor.baseAddress, surfaceBytes);
            const auto commands = recorder.Commands();
            RecordMemoryBarrier(context, commands, VK_PIPELINE_STAGE_ALL_COMMANDS_BIT | VK_PIPELINE_STAGE_HOST_BIT, VK_PIPELINE_STAGE_TRANSFER_BIT, VK_ACCESS_HOST_WRITE_BIT | VK_ACCESS_TRANSFER_WRITE_BIT, VK_ACCESS_TRANSFER_WRITE_BIT);
            context.Function<PFN_vkCmdFillBuffer>("vkCmdFillBuffer")(commands, import->buffer, descriptor.baseAddress - import->base, surfaceBytes, 0x77777777u);
            recorder.NotePendingWrite(descriptor.baseAddress, surfaceBytes);
            Memory::MarkWritten(descriptor.baseAddress, surfaceBytes);
        }
        image = std::make_shared<StorageTexture>(context, *context.detiler, descriptor, 0);
        if (!defer) Sync();
        Require(image->Generation() != 0, "edge image has no tracked upload generation");
        Require(Memory::UnchangedSince(descriptor.baseAddress, surfaceBytes, image->Generation()), "edge upload did not establish a current generation");
    }

    ~Surface() {
        recorder.Sync();
        alias.reset();
        image.reset();
        {
            GuestAllocations::Mutation mutation;
            mutation.Remove(allocation);
        }
        HostImportFor(context, reinterpret_cast<std::uint64_t>(allocation), allocationBytes);
#ifdef _WIN32
        GuestArena::GuestArenaReset_nid_postfix(allocation, allocationBytes);
        GuestArena::GuestArenaRelease_nid_postfix(allocation, allocationBytes);
#else
        GuestWriteWatch::GuestWriteWatchUnregister_nid_postfix(allocation, allocationBytes);
        munmap(allocation, allocationBytes);
#endif
    }

    void Draw(std::uint8_t value, bool defer = false, bool aliased = false) {
        const auto& target = aliased ? alias : image;
        Require(target != nullptr, "the image draw fixture is not created");
        const auto commands = recorder.Commands();
        recorder.Keep(target);
        const VkImageSubresourceRange range{VK_IMAGE_ASPECT_COLOR_BIT, 0, 1, 0, 1};
        VkClearColorValue clear{{static_cast<float>(value) / 255.0f, 0.0f, 0.0f, 1.0f}};
        if (aliased) clear.uint32[0] = value;
        RecordMemoryBarrier(context, commands, VK_PIPELINE_STAGE_ALL_COMMANDS_BIT, VK_PIPELINE_STAGE_TRANSFER_BIT, VK_ACCESS_SHADER_READ_BIT | VK_ACCESS_SHADER_WRITE_BIT | VK_ACCESS_TRANSFER_WRITE_BIT, VK_ACCESS_TRANSFER_WRITE_BIT);
        context.Function<PFN_vkCmdClearColorImage>("vkCmdClearColorImage")(commands, target->Image(), VK_IMAGE_LAYOUT_GENERAL, &clear, 1, &range);
        RecordMemoryBarrier(context, commands, VK_PIPELINE_STAGE_TRANSFER_BIT, VK_PIPELINE_STAGE_ALL_COMMANDS_BIT, VK_ACCESS_TRANSFER_WRITE_BIT, VK_ACCESS_SHADER_READ_BIT | VK_ACCESS_SHADER_WRITE_BIT | VK_ACCESS_TRANSFER_READ_BIT);
        target->MarkDirty();
        if (!defer) Sync();
    }

    void CpuStore(std::size_t at, std::byte value, bool aliased = false) {
        const auto& target = aliased ? alias : image;
        Require(target != nullptr, "the CPU store fixture is not created");
        Require(at < surfaceBytes, "CPU edge store is outside the surface");
        *reinterpret_cast<volatile std::byte*>(descriptor.baseAddress + at) = value;
        noteWrite(descriptor.baseAddress + at, 1);
        Memory::CollectWritesUncached(descriptor.baseAddress + at, 1);
        Require(Memory::WrittenSince(descriptor.baseAddress + at, 1, target->Generation()), "CPU edge store did not acquire a newer write stamp");
    }

    void CpuStoreUncollected(std::size_t at, std::byte value) {
        Require(at < surfaceBytes, "uncollected CPU edge store is outside the surface");
        Require(Memory::UnchangedSince(descriptor.baseAddress, surfaceBytes, image->Generation()), "uncollected CPU fixture already has a newer write stamp");
        const auto before = Memory::TrackerGeneration();
        *reinterpret_cast<volatile std::byte*>(descriptor.baseAddress + at) = value;
        noteWrite(descriptor.baseAddress + at, 1);
        Require(Memory::TrackerGeneration() == before, "an uncollected CPU store advanced the write tracker");
        Require(Memory::UnchangedSince(descriptor.baseAddress, surfaceBytes, image->Generation()), "an uncollected CPU store reached the tracker before refresh");
    }

    void StoreNeighbour() {
        Require(offset >= 4096, "test surface has no head neighbour");
        auto* bytes = static_cast<volatile std::byte*>(allocation);
        bytes[16] = std::byte{0x41};
        noteWrite(reinterpret_cast<std::uintptr_t>(allocation) + 16, 1);
        Memory::CollectWritesUncached(reinterpret_cast<std::uint64_t>(allocation), 4096);
        neighbours[16] = std::byte{0x41};
    }

    void DriverStore(std::size_t at, std::byte value) {
        const auto address = descriptor.baseAddress + at;
        const auto* import = HostImportFor(context, address, 4);
        Require(import != nullptr, "driver edge store lost its host import");
        const std::array bytes{value, value, value, value};
        recorder.RecordStore(import->buffer, address - import->base, bytes, address);
        recorder.NotePendingWrite(address, bytes.size());
        Require(Memory::MarkWritten(address, bytes.size()) > image->Generation(), "driver edge store did not acquire a newer stamp");
    }

    void Reregister() {
        GuestAllocations::Mutation mutation;
        mutation.Remove(allocation);
        mutation.Add(allocation, allocationBytes, true, true);
    }

    void WriteBack(bool aliased = false) {
        const auto& target = aliased ? alias : image;
        Require(target != nullptr, "the write-back fixture is not created");
        target->WriteBack();
        Sync();
    }

    void Refresh() {
        image->Refresh();
        Sync();
    }

    void CreateAlias() {
        image->SetCached(true);
        auto resource = descriptor;
        resource.format = 5;
        alias = std::make_shared<StorageTexture>(context, *context.detiler, resource, 0);
        Sync();
    }

    void RefreshAlias() {
        Require(alias != nullptr, "the alias fixture is not created");
        alias->Refresh();
        Sync();
    }

    void Fill(std::uint8_t value, bool defer = false) {
        const std::uint32_t repeated = static_cast<std::uint32_t>(value) * 0x01010101u;
        const std::array pattern{repeated, repeated, repeated, repeated};
        const char* refusal = nullptr;
        const bool cleared = image->FillClear(pattern, StorageTexture::WholeImage, refusal);
        Require(cleared, std::string("edge fill fixture was refused: ") + (refusal != nullptr ? refusal : "unknown"));
        if (!defer) Sync();
    }

    void CopyFrom(Surface& source, bool defer = false) {
        image->SetCached(true);
        source.image->SetCached(true);
        const char* refusal = nullptr;
        const bool copied = image->CopyFrom(*source.image, refusal);
        Require(copied, std::string("edge copy fixture was refused: ") + (refusal != nullptr ? refusal : "unknown"));
        if (!defer) Sync();
    }

    void CheckMemory(std::byte expected, const std::map<std::size_t, std::byte>& exceptions, const std::string& what) {
        std::vector<std::byte> bytes(allocationBytes);
        Memory::Read(reinterpret_cast<std::uint64_t>(allocation), bytes);
        for (std::size_t at = 0; at < allocationBytes; ++at) {
            auto wanted = Neighbour;
            if (at >= offset && at < offset + surfaceBytes) {
                const auto found = exceptions.find(at - offset);
                wanted = found == exceptions.end() ? expected : found->second;
            } else if (const auto found = neighbours.find(at); found != neighbours.end()) {
                wanted = found->second;
            }
            if (bytes[at] != wanted) throw std::runtime_error(what + ": byte " + std::to_string(at) + " expected " + std::to_string(std::to_integer<unsigned>(wanted)) + " got " + std::to_string(std::to_integer<unsigned>(bytes[at])));
        }
    }

    void CheckImage(std::byte expected, const std::map<std::byte, std::size_t>& exceptions, const std::string& what, bool aliased = false) {
        const auto& source = aliased ? alias : image;
        Require(source != nullptr, "the image readback fixture is not created");
        const auto texelBytes = static_cast<std::size_t>(descriptor.width) * descriptor.height;
        Buffer readback(context, texelBytes, VK_BUFFER_USAGE_TRANSFER_DST_BIT);
        const auto commands = recorder.Commands();
        RecordMemoryBarrier(context, commands, VK_PIPELINE_STAGE_ALL_COMMANDS_BIT, VK_PIPELINE_STAGE_TRANSFER_BIT, VK_ACCESS_SHADER_WRITE_BIT | VK_ACCESS_TRANSFER_WRITE_BIT, VK_ACCESS_TRANSFER_READ_BIT);
        VkBufferImageCopy copy{};
        copy.imageSubresource = {VK_IMAGE_ASPECT_COLOR_BIT, 0, 0, 1};
        copy.imageExtent = {descriptor.width, descriptor.height, 1};
        context.Function<PFN_vkCmdCopyImageToBuffer>("vkCmdCopyImageToBuffer")(commands, source->Image(), VK_IMAGE_LAYOUT_GENERAL, readback.Handle(), 1, &copy);
        RecordMemoryBarrier(context, commands, VK_PIPELINE_STAGE_TRANSFER_BIT, VK_PIPELINE_STAGE_HOST_BIT, VK_ACCESS_TRANSFER_WRITE_BIT, VK_ACCESS_HOST_READ_BIT);
        Sync();
        std::map<std::byte, std::size_t> counts;
        for (const auto byte : readback.Bytes().first(texelBytes)) {
            if (byte != expected) ++counts[byte];
        }
        Require(counts == exceptions, what + ": image does not contain the merged texels");
    }

    std::size_t Size() const { return surfaceBytes; }
    std::uint64_t Address() const { return descriptor.baseAddress; }
    std::uint64_t Generation() const { return image->Generation(); }

private:
    void Sync() {
        recorder.Submit();
        Check(context.Function<PFN_vkQueueWaitIdle>("vkQueueWaitIdle")(context.queue), "vkQueueWaitIdle edge test");
        recorder.Sync();
    }

    Context context;
    Recorder& recorder;
    std::size_t offset;
    std::size_t surfaceBytes = 0;
    std::size_t allocationBytes = 0;
    void* allocation = nullptr;
    GuestTextureResource descriptor{};
    std::shared_ptr<StorageTexture> image;
    std::shared_ptr<StorageTexture> alias;
    std::map<std::size_t, std::byte> neighbours;
};

void noOpEdgeTests(const Context& context, Recorder& recorder) {
    for (const bool refresh : {false, true}) {
        Surface surface(context, recorder, 8192);
        surface.Draw(128);
        surface.CpuStore(32, Initial);
        surface.CpuStore(surface.Size() - 32, Initial);
        surface.StoreNeighbour();
        if (refresh) {
            surface.Refresh();
            surface.CheckImage(std::byte{128}, {}, "no-op CPU edge store during refresh");
        } else {
            surface.WriteBack();
        }
        surface.CheckMemory(std::byte{128}, {}, "no-op CPU edge store discarded GPU results");
    }
}

void mixedEdgeTests(const Context& context, Recorder& recorder) {
    Surface surface(context, recorder, 8192);
    surface.Draw(128);
    surface.CpuStore(17, std::byte{0x31});
    surface.CpuStore(surface.Size() - 23, std::byte{0x32});
    surface.CpuStore(4096 + 17, Initial);
    surface.StoreNeighbour();
    surface.WriteBack();
    surface.CheckMemory(std::byte{128}, {{17, std::byte{0x31}}, {surface.Size() - 23, std::byte{0x32}}}, "mixed CPU and GPU edge writes");
    surface.Refresh();
    surface.CheckImage(std::byte{128}, {{std::byte{0x31}, 1}, {std::byte{0x32}, 1}}, "mixed edge refresh");
    surface.Draw(64);
    surface.CpuStore(17, std::byte{0x31});
    surface.CpuStore(surface.Size() - 23, std::byte{0x52});
    surface.WriteBack();
    surface.CheckMemory(std::byte{64}, {{surface.Size() - 23, std::byte{0x52}}}, "second edge write-back reused an obsolete baseline");
}

void shortSurfaceTests(const Context& context, Recorder& recorder) {
    for (const std::size_t offset : {0, 8192}) {
        for (const bool refresh : {false, true}) {
            for (const bool collected : {true, false}) {
                for (const bool changed : {false, true}) {
                    Surface surface(context, recorder, offset, 64, 64);
                    Require(surface.Size() == 4096, "short edge fixture is not one page");
                    surface.Draw(128);
                    if (collected) {
                        surface.CpuStore(32, Initial);
                        if (changed) surface.CpuStore(17, std::byte{0x31});
                    } else {
                        surface.CpuStoreUncollected(32, Initial);
                        if (changed) surface.CpuStoreUncollected(17, std::byte{0x31});
                    }
                    const std::map<std::byte, std::size_t> texels = changed ? std::map<std::byte, std::size_t>{{std::byte{0x31}, 1}} : std::map<std::byte, std::size_t>{};
                    const std::map<std::size_t, std::byte> memory = changed ? std::map<std::size_t, std::byte>{{17, std::byte{0x31}}} : std::map<std::size_t, std::byte>{};
                    if (refresh) {
                        surface.Refresh();
                        surface.CheckImage(std::byte{128}, texels, "refresh discarded a short edge surface");
                    }
                    surface.CheckMemory(std::byte{128}, memory, "a read hook discarded a whole short edge surface");
                }
            }
        }
    }
}

void fullBlockTests(const Context& context, Recorder& recorder) {
    Surface surface(context, recorder, 0);
    surface.Draw(128);
    surface.CpuStore(32, Initial);
    surface.WriteBack();
    std::map<std::size_t, std::byte> kept;
    for (std::size_t at = 0; at < UnitBytes; ++at) kept.emplace(at, Initial);
    surface.CheckMemory(std::byte{128}, kept, "an aligned CPU-stamped block changed ownership");
}

void uploadOrderTests(const Context& context, Recorder& recorder) {
    Surface surface(context, recorder, 8192, 512, 512, true);
    surface.Draw(128);
    surface.CpuStore(32, std::byte{0x77});
    surface.CpuStore(surface.Size() - 32, std::byte{0x77});
    surface.WriteBack();
    surface.CheckMemory(std::byte{128}, {}, "edge baseline preceded an ordered GPU upload source write");
}

void writeBackBaselineTests(const Context& context, Recorder& recorder) {
    for (const bool cpu : {false, true}) {
        for (const bool shortSurface : {false, true}) {
            Surface surface(context, recorder, shortSurface ? 0 : 8192, shortSurface ? 64 : 512, shortSurface ? 64 : 512, false, cpu);
            surface.Draw(128);
            surface.WriteBack();
            surface.Draw(64);
            surface.CpuStore(32, std::byte{128});
            surface.WriteBack();
            surface.CheckMemory(std::byte{64}, {}, "a normal write-back did not renew the edge baseline");
        }
    }
}

void driverStoreTests(const Context& context, Recorder& recorder) {
    for (const bool cpu : {false, true}) {
        Surface surface(context, recorder, 8192);
        surface.Draw(128);
        if (cpu) surface.CpuStore(17, std::byte{0x31});
        surface.DriverStore(64, Initial);
        surface.WriteBack();
        std::map<std::size_t, std::byte> kept;
        for (std::size_t at = 0; at < UnitBytes - 8192; ++at) kept.emplace(at, Initial);
        if (cpu) kept[17] = std::byte{0x31};
        surface.CheckMemory(std::byte{128}, kept, "a same-value ordered driver store lost edge ownership");
    }
}

void untrackedDriverProvenanceTests() {
    constexpr std::uint64_t outside = 0;
    constexpr std::size_t bytes = 64;
    Require(!Memory::Watched(outside, bytes), "the untracked driver-store range is watched");
    Require(Memory::DriverStoredOver(outside, bytes, Memory::TrackerGeneration()), "an untracked range claims no driver store");
    Require(!Memory::DriverStoredOver(outside, 0, 0), "an empty unknown range contains a driver store");
    std::cout << "Untracked driver provenance tests passed\n";
}

void driverProvenanceTests(const Context& context, Recorder& recorder) {
    Surface surface(context, recorder, 8192);
    const auto address = surface.Address();
    const auto generation = surface.Generation();
    Require(!Memory::DriverStoredOver(address, 64, generation), "an untouched edge has a driver store");
    surface.CpuStore(32, Initial);
    Require(!Memory::DriverStoredOver(address, 64, generation), "a CPU-only write was attributed to the driver");
    Require(Memory::MarkWritten(address + 512, 4) > generation, "the driver piece was not stamped");
    Require(Memory::DriverStoredOver(address + 512, 4, generation), "an exact driver store was forgotten");
    Require(!Memory::DriverStoredOver(address, 64, generation), "a disjoint driver piece owns the CPU-written edge");
    const auto whole = address + UnitBytes - 8192;
    Require(Memory::MarkWritten(whole, UnitBytes) > generation, "the whole driver block was not stamped");
    surface.CpuStore(UnitBytes - 8192 + 8, Initial);
    Require(Memory::DriverStoredOver(whole, 16, generation), "a later CPU stamp erased a whole driver store");
    const auto history = Memory::TrackerGeneration();
    const auto pieces = whole + UnitBytes;
    for (std::uint64_t piece = 0; piece < 6; ++piece) Memory::MarkWritten(pieces + piece * 64, 4);
    Require(Memory::DriverStoredOver(pieces, 4, history), "evicted newer driver history was treated as no store");
    Require(Memory::DriverStoredOver(address, 64, 0), "an unknown baseline generation claims no driver store");
    const auto huge = std::numeric_limits<std::size_t>::max() - static_cast<std::size_t>(address);
    Require(Memory::DriverStoredOver(address, huge, generation), "a huge uncovered range claims no driver store");
    Require(Memory::DriverStoredOver(address, std::numeric_limits<std::size_t>::max(), generation), "an overflowing range claims no driver store");
    Require(!Memory::DriverStoredOver(address, 0, generation), "an empty watched range contains a driver store");
}

void reregisteredEdgeTests(const Context& context, Recorder& recorder) {
    Surface surface(context, recorder, 8192, 64, 64);
    surface.Draw(128);
    surface.Reregister();
    surface.CpuStore(32, Initial);
    surface.WriteBack();
    surface.CheckMemory(Initial, {}, "a retired edge baseline overwrote a replacement allocation");
}

void aliasEdgeTests(const Context& context, Recorder& recorder) {
    for (const bool collected : {true, false}) {
        for (const bool changed : {false, true}) {
            Surface surface(context, recorder, 0, 64, 64);
            surface.CreateAlias();
            surface.Draw(128);
            if (collected) {
                surface.CpuStore(32, Initial);
                if (changed) surface.CpuStore(17, std::byte{0x31});
            } else {
                surface.CpuStoreUncollected(32, Initial);
                if (changed) surface.CpuStoreUncollected(17, std::byte{0x31});
            }
            surface.RefreshAlias();
            const std::map<std::byte, std::size_t> texels = changed ? std::map<std::byte, std::size_t>{{std::byte{0x31}, 1}} : std::map<std::byte, std::size_t>{};
            const std::map<std::size_t, std::byte> memory = changed ? std::map<std::size_t, std::byte>{{17, std::byte{0x31}}} : std::map<std::size_t, std::byte>{};
            const std::string state = collected ? "collected" : "uncollected";
            surface.CheckImage(std::byte{128}, texels, "an alias lost " + state + " CPU edge writes", true);
            surface.CheckMemory(std::byte{128}, memory, "an alias refreshed from stale " + state + " edge bytes");
        }
    }
}

void aliasBorrowWriteTests(const Context& context, Recorder& recorder) {
    Surface surface(context, recorder, 0, 64, 64);
    surface.CreateAlias();
    surface.Draw(128);
    surface.RefreshAlias();
    surface.CheckImage(std::byte{128}, {}, "an alias did not borrow pending GPU results", true);
    surface.Draw(64, false, true);
    surface.CpuStore(32, Initial, true);
    surface.WriteBack(true);
    surface.CheckMemory(std::byte{64}, {}, "a write after an alias borrow lost the physical edge baseline");
}

void cpuFallbackTests(const Context& context, Recorder& recorder) {
    for (const bool shortSurface : {false, true}) {
        Surface surface(context, recorder, shortSurface ? 0 : 8192, shortSurface ? 64 : 512, shortSurface ? 64 : 512, false, true);
        surface.Draw(128);
        surface.CpuStore(32, Initial);
        surface.CpuStore(17, std::byte{0x31});
        surface.CpuStore(surface.Size() - 23, std::byte{0x32});
        surface.WriteBack();
        surface.CheckMemory(std::byte{128}, {{17, std::byte{0x31}}, {surface.Size() - 23, std::byte{0x32}}}, "CPU fallback lost mixed edge writes");
        surface.Refresh();
        surface.CheckImage(std::byte{128}, {{std::byte{0x31}, 1}, {std::byte{0x32}, 1}}, "CPU fallback edge refresh");
        surface.Draw(64);
        surface.CpuStore(17, std::byte{0x31});
        surface.CpuStore(surface.Size() - 23, std::byte{0x32});
        surface.WriteBack();
        surface.CheckMemory(std::byte{64}, {}, "CPU fallback reused a stale merged edge baseline");
    }
}

void pendingEdgeTests(const Context& context, Recorder& recorder) {
    for (const bool shortSurface : {false, true}) {
        Surface surface(context, recorder, shortSurface ? 0 : 8192, shortSurface ? 64 : 512, shortSurface ? 64 : 512, false, false, true);
        surface.Draw(128, true);
        surface.CpuStoreUncollected(17, std::byte{0x31});
        surface.CpuStoreUncollected(32, Initial);
        surface.CpuStoreUncollected(surface.Size() - 32, Initial);
        surface.WriteBack();
        surface.CheckMemory(std::byte{128}, {{17, std::byte{0x31}}}, "a pending upload captured a later CPU edit as its baseline");
    }
}

void fillEdgeTests(const Context& context, Recorder& recorder) {
    for (const bool shortSurface : {false, true}) {
        for (const bool draw : {false, true}) {
            Surface surface(context, recorder, shortSurface ? 0 : 8192, shortSurface ? 64 : 512, shortSurface ? 64 : 512);
            surface.Fill(128);
            surface.CheckImage(std::byte{128}, {}, "a GPU fill did not clear the edge image");
            if (draw) surface.Draw(64);
            surface.CpuStore(32, Initial);
            surface.WriteBack();
            surface.CheckMemory(draw ? std::byte{64} : std::byte{128}, {}, "a GPU fill lost the physical edge baseline");
        }
    }
}

void copyEdgeTests(const Context& context, Recorder& recorder) {
    for (const bool draw : {false, true}) {
        Surface source(context, recorder, 0, 64, 64);
        Surface destination(context, recorder, 0, 64, 64);
        source.Draw(128);
        destination.CopyFrom(source);
        destination.CheckImage(std::byte{128}, {}, "a GPU copy did not copy the edge image");
        if (draw) destination.Draw(64);
        destination.CpuStore(32, Initial);
        destination.WriteBack();
        destination.CheckMemory(draw ? std::byte{64} : std::byte{128}, {}, "a GPU copy lost the destination's physical edge baseline");
    }
}

void pendingFillEdgeTests(const Context& context, Recorder& recorder) {
    for (const bool shortSurface : {false, true}) {
        for (const bool priorWrite : {false, true}) {
            Surface surface(context, recorder, shortSurface ? 0 : 8192, shortSurface ? 64 : 512, shortSurface ? 64 : 512);
            if (priorWrite) surface.DriverStore(32, std::byte{0x77});
            surface.Fill(128, true);
            surface.CpuStoreUncollected(17, std::byte{0x31});
            surface.CpuStoreUncollected(32, priorWrite ? std::byte{0x77} : Initial);
            surface.WriteBack();
            surface.CheckMemory(std::byte{128}, {{17, std::byte{0x31}}}, "a pending fill captured a later CPU write as its baseline");
        }
    }
}

void pendingCopyEdgeTests(const Context& context, Recorder& recorder) {
    for (const bool shortSurface : {false, true}) {
        for (const bool priorWrite : {false, true}) {
            Surface source(context, recorder, shortSurface ? 0 : 8192, shortSurface ? 64 : 512, shortSurface ? 64 : 512);
            Surface destination(context, recorder, shortSurface ? 0 : 8192, shortSurface ? 64 : 512, shortSurface ? 64 : 512);
            source.Draw(128);
            if (priorWrite) destination.DriverStore(32, std::byte{0x77});
            destination.CopyFrom(source, true);
            destination.CpuStoreUncollected(17, std::byte{0x31});
            destination.CpuStoreUncollected(32, priorWrite ? std::byte{0x77} : Initial);
            destination.WriteBack();
            destination.CheckMemory(std::byte{128}, {{17, std::byte{0x31}}}, "a pending copy captured a later CPU write as its baseline");
        }
    }
}


void mergePrecedenceTests(const Context& context, Recorder& recorder) {
    Surface surface(context, recorder, 8192);
    constexpr std::size_t count = 65536;
    std::vector<std::byte> baseline(count), current(count), expected(count);
    auto* destination = reinterpret_cast<std::byte*>(surface.Address());
    for (unsigned value = 0; value < 256; ++value) {
        std::fill(baseline.begin(), baseline.end(), std::byte{static_cast<unsigned char>(value)});
        for (std::size_t byte = 0; byte < count; ++byte) {
            const auto cpu = static_cast<unsigned char>(byte / 256);
            const auto gpu = static_cast<unsigned char>(byte % 256);
            destination[byte] = std::byte{cpu};
            current[byte] = std::byte{gpu};
            expected[byte] = std::byte{cpu == value && gpu != value ? gpu : cpu};
        }
        noteWrite(surface.Address(), count);
        const auto generation = Memory::CollectWritesUncached(surface.Address(), count);
        Require(Memory::MergeChangedCommitted(surface.Address(), current, baseline, generation), "a CPU-only byte merge was refused");
        Require(std::equal(expected.begin(), expected.end(), destination), "a CPU/GPU byte merge violated baseline precedence");
    }
}

void mergeDriverPrecedenceTests(const Context& context, Recorder& recorder) {
    for (const auto value : {Initial, std::byte{0x77}}) {
        Surface surface(context, recorder, 8192, 64, 64);
        const auto generation = surface.Generation();
        surface.DriverStore(0, value);
        surface.WriteBack();
        surface.CpuStore(7, std::byte{0x31});
        std::array<std::byte, 8> baseline, current;
        baseline.fill(Initial);
        current.fill(std::byte{128});
        Require(!Memory::MergeChangedCommitted(surface.Address(), current, baseline, generation), "a newer driver store permitted a stale byte merge");
        surface.CheckMemory(Initial, {{0, value}, {1, value}, {2, value}, {3, value}, {7, std::byte{0x31}}}, "a refused merge changed driver or CPU bytes");
    }
}

void edgePrecedenceTests(const Context& context, Recorder& recorder) {
    for (const bool cpuFirst : {true, false}) {
        Surface surface(context, recorder, 8192, 64, 64);
        if (cpuFirst) surface.CpuStore(17, std::byte{0x31});
        surface.Draw(128);
        if (!cpuFirst) surface.CpuStore(17, std::byte{0x31});
        surface.CpuStore(19, std::byte{0x33});
        surface.CpuStore(19, Initial);
        surface.WriteBack();
        surface.CheckMemory(std::byte{128}, {{17, std::byte{0x31}}}, "mixed CPU/GPU edge result differs");
        surface.CpuStore(18, std::byte{0x32});
        surface.Refresh();
        surface.CheckImage(std::byte{128}, {{std::byte{0x31}, 1}, {std::byte{0x32}, 1}}, "a CPU edit after the edge merge was lost");
    }
    Surface surface(context, recorder, 8192, 64, 64);
    surface.Draw(205);
    surface.CpuStore(17, std::byte{0x31});
    surface.CpuStore(18, Initial);
    surface.WriteBack();
    surface.CheckMemory(Initial, {{17, std::byte{0x31}}}, "an unchanged GPU result overwrote a CPU edit");
    surface.Refresh();
    surface.CheckImage(Initial, {{std::byte{0x31}, 1}}, "an unchanged GPU result lost a CPU edit at refresh");
}

}

int main() {
    try {
        untrackedDriverProvenanceTests();
        std::unique_ptr<AgcDriver::Tests::RecorderDevice> device;
        try {
            device = std::make_unique<AgcDriver::Tests::RecorderDevice>();
            Require(device->GetContext().hostImportAlignment != 0, "edge write-back tests require Vulkan host imports");
            Require(Memory::WriteWatched(), "edge write-back tests require page write tracking");
        } catch (const std::exception& error) {
            if (std::getenv("ANYPS5_REQUIRE_VULKAN") != nullptr) throw;
            std::cout << "skipped, no usable Vulkan device or write tracking: " << error.what() << '\n';
            return 77;
        }
        std::lock_guard lock(Memory::GpuMutex());
        const auto& base = device->GetContext();
        SetImportWatch(base, ImportWatch::Watch);
        TextureDetiler detiler(base);
        auto context = base;
        context.detiler = &detiler;
        Recorder recorder(context);
        recorder.Activate();
        noOpEdgeTests(context, recorder);
        mixedEdgeTests(context, recorder);
        shortSurfaceTests(context, recorder);
        fullBlockTests(context, recorder);
        uploadOrderTests(context, recorder);
        writeBackBaselineTests(context, recorder);
        driverStoreTests(context, recorder);
        driverProvenanceTests(context, recorder);
        mergePrecedenceTests(context, recorder);
        mergeDriverPrecedenceTests(context, recorder);
        edgePrecedenceTests(context, recorder);
        reregisteredEdgeTests(context, recorder);
        aliasEdgeTests(context, recorder);
        aliasBorrowWriteTests(context, recorder);
        cpuFallbackTests(context, recorder);
        pendingEdgeTests(context, recorder);
        fillEdgeTests(context, recorder);
        copyEdgeTests(context, recorder);
        pendingFillEdgeTests(context, recorder);
        pendingCopyEdgeTests(context, recorder);
        recorder.Sync();
        std::cout << "Storage edge write-back tests passed\n";
    } catch (const std::exception& error) {
        std::cerr << "Storage edge write-back test failed: " << error.what() << '\n';
        return 1;
    }
    return 0;
}
