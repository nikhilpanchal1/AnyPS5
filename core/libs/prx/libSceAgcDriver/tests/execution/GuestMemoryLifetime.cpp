#include "prx/libSceAgcDriver/tests/GuestMemoryLifetimeSupport.hpp"
#include "prx/libc/include/ApplicationHeap.hpp"
#include <string_view>
using namespace GuestMemoryLifetime;

extern "C" {
void* APS5_VABI mmap_nid_postfix(void*, std::size_t, int, int, int, std::int64_t) noexcept;
int APS5_VABI munmap_nid_postfix(void*, std::size_t) noexcept;
int APS5_VABI mprotect_nid_postfix(void*, std::size_t, int) noexcept;
void* APS5_VABI memalign_nid_postfix(std::size_t, std::size_t);
void* APS5_VABI realloc_nid_postfix(void*, std::size_t);
void APS5_VABI free_nid_postfix(void*);
int APS5_VABI sceKernelMapFlexibleMemory(void**, std::size_t, int, int);
int APS5_VABI sceKernelAllocateDirectMemory(std::int64_t, std::int64_t, std::size_t, std::size_t, int, std::int64_t*);
int APS5_VABI sceKernelMapDirectMemory(void**, std::size_t, int, int, std::int64_t, std::size_t);
int APS5_VABI sceKernelReleaseDirectMemory(std::int64_t, std::size_t);
}

namespace {
void* Map(std::size_t bytes = BlockBytes) {
    auto* pointer = mmap_nid_postfix(nullptr, bytes, 3, 0x1002, -1, 0);
    Require(pointer != reinterpret_cast<void*>(~std::uintptr_t{0}), "guest mmap failed");
    Require(Access(pointer, false), "guest mmap did not register CPU-only read/write access");
    std::memset(pointer, 0, bytes);
    return pointer;
}

void Unmap(AgcDriver::VulkanDevice& device, void* pointer) {
    Require(munmap_nid_postfix(pointer, BlockBytes) == 0, "guest unmap failed");
    Require(!Imported(device, pointer), "host import survived guest unmap");
}

void CheckProtection(AgcDriver::VulkanDevice& device, void* pointer) {
    for (int protection : {3, 1}) {
        Require(Fill(device, pointer), "GPU fill did not create a host import");
        Require(mprotect_nid_postfix(pointer, BlockBytes, protection) == 0, "guest protection change failed");
        Require(!Imported(device, pointer), "host import survived guest protection change");
        Require(Verify(pointer), "guest protection lost the pending GPU fill");
    }
}

void Copy(AgcDriver::VulkanDevice& device, void* destination, const void* source, std::size_t importBytes = BlockBytes) {
    const auto copied = device.CopyBuffer(Address(destination), Address(source), FillBytes, 0, BlockBytes, 0, 0, 0, [](std::span<const std::byte>, std::uint64_t) {});
    Require(copied.path == 1, "copy did not use a Vulkan host-import transfer");
    Require(Imported(device, source, importBytes) && Imported(device, destination, importBytes), "GPU copy did not import both ranges");
}

void CheckMappings(AgcDriver::VulkanDevice& device) {
    auto* mapping = Map();
    CheckProtection(device, mapping);
    Require(mprotect_nid_postfix(mapping, BlockBytes, 0) == 0, "guest inaccessible protection failed");
    Require(mprotect_nid_postfix(mapping, BlockBytes, 3) == 0, "guest writable protection restore failed");
    Require(Verify(mapping), "guest protection restore lost the GPU fill");
    Require(Fill(device, mapping), "GPU fill did not create a host import");
    void* replaced = mapping;
    Require(sceKernelMapFlexibleMemory(&replaced, BlockBytes, 0x33, 0x10) == 0 && replaced == mapping, "guest fixed mapping replacement failed");
    Require(!Imported(device, mapping), "host import survived guest fixed mapping replacement");
    Require(Access(mapping, true), "guest fixed mapping lacks CPU and GPU access");
    Require(Verify(mapping, true, BlockBytes), "GPU work reached replacement guest pages");
    Require(Fill(device, mapping), "replacement GPU fill did not create a host import");
    Unmap(device, mapping);

    mapping = Map(3 * BlockBytes);
    Require(Fill(device, mapping), "GPU fill did not create a host import");
    auto* middle = static_cast<std::uint8_t*>(mapping) + BlockBytes;
    Require(mprotect_nid_postfix(middle, BlockBytes, 1) == 0, "guest partial protection failed");
    Require(!Imported(device, mapping), "whole host import survived partial protection change");
    Require(Verify(mapping), "partial protection lost the pending GPU fill");
    Require(Fill(device, mapping), "prefix GPU fill did not create a host import");
    Unmap(device, middle);
    Require(Imported(device, mapping), "unrelated prefix import was retired by middle unmap");
    Unmap(device, mapping);
    Unmap(device, middle + BlockBytes);
}

void CheckHeap(AgcDriver::VulkanDevice& device) {
    const std::array<void*, 10> api{};
    ApplicationHeapRegister_nid_no_patch(api.data());
    for (int iteration = 0; iteration < 4; ++iteration) {
        auto* allocation = memalign_nid_postfix(BlockBytes, BlockBytes);
        Require(allocation != nullptr, "guest aligned allocation failed");
        std::memset(allocation, 0, BlockBytes);
        Require(Fill(device, allocation), "heap GPU fill did not create a host import");
        if (iteration == 0) {
            auto* replacement = realloc_nid_postfix(allocation, 2 * BlockBytes);
            Require(replacement != nullptr, "guest realloc failed");
            Require(!Imported(device, allocation), "host import survived guest realloc");
            Require(Verify(replacement), "guest realloc lost the pending GPU fill");
            allocation = replacement;
        }
        free_nid_postfix(allocation);
        Require(!Imported(device, allocation), "host import survived guest free or heap cache eviction");
    }
}

void CheckLockedMutation(AgcDriver::VulkanDevice& device) {
    auto* mapping = Map();
    {
        std::lock_guard outer(GpuMutex());
        CheckProtection(device, mapping);
        Unmap(device, mapping);
    }
    mapping = Map();
    {
        std::lock_guard outer(GpuMutex());
        auto lease = std::make_shared<GuestAllocations::Lease>(GuestAllocations::GuestAllocationsAcquire_nid_postfix());
        auto* recorder = AgcDriver::Graphics::Recorder::Active();
        Require(recorder != nullptr, "Vulkan device has no active recorder");
        recorder->Keep(std::move(lease));
        Unmap(device, mapping);
    }
}

void CheckCopy(AgcDriver::VulkanDevice& device) {
    auto* source = Map();
    auto* destination = Map();
    for (bool unmap : {false, true}) {
        {
            std::lock_guard lock(GpuMutex());
            Require(Fill(device, source), "copy source GPU fill did not create a host import");
            Copy(device, destination, source);
        }
        if (unmap) Unmap(device, source);
        else Require(mprotect_nid_postfix(source, BlockBytes, 3) == 0, "copied source protection refresh failed");
        Require(!Imported(device, source), "GPU copy source remained imported after guest mutation");
        Require(Verify(destination), "guest mutation lost the GPU copy");
        Require(Imported(device, destination), "source retirement retired the unrelated destination");
    }
    Unmap(device, destination);
}

void CheckDirectRelease(AgcDriver::VulkanDevice& device) {
    std::int64_t physical = 0;
    Require(sceKernelAllocateDirectMemory(0, 0x7fffffffffll, BlockBytes, BlockBytes, 0, &physical) == 0, "guest direct allocation failed");
    std::array<void*, 2> views{};
    for (auto& view : views) {
        Require(sceKernelMapDirectMemory(&view, BlockBytes, 0x33, 0, physical, BlockBytes) == 0, "direct view mapping failed");
        Require(Access(view, true), "direct view lacks CPU and GPU access");
    }
    Require(views[0] != views[1], "direct views have the same address");
    std::memset(views[0], 0, BlockBytes);
    static_cast<std::uint8_t*>(views[0])[BlockBytes - 1] = 0x5a;
    Require(static_cast<const std::uint8_t*>(views[1])[BlockBytes - 1] == 0x5a, "direct views do not share physical backing");
    auto* destination = static_cast<std::byte*>(Map());
    {
        std::lock_guard lock(GpuMutex());
        for (std::size_t i = 0; i < views.size(); ++i)
            Require(Fill(device, static_cast<std::byte*>(views[i]) + i * FillBytes, FillBytes), "direct view GPU fill failed");
        for (std::size_t i = 0; i < views.size(); ++i)
            Copy(device, destination + i * FillBytes, static_cast<const std::byte*>(views[i]) + i * FillBytes, FillBytes);
        Require(Imported(device, views[0]) && Imported(device, views[1]), "both direct view imports were not retained before release");
    }
    Require(sceKernelReleaseDirectMemory(physical, BlockBytes) == 0, "guest direct release failed");
    for (std::size_t i = 0; i < views.size(); ++i) {
        Require(!Imported(device, views[i]), "direct release retained an imported view");
        Require(!AgcDriver::Graphics::RegisteredReadableCovers(Address(views[i]), BlockBytes), "direct release left a view registered");
        Require(Verify(destination + i * FillBytes), "direct release lost the GPU copy");
    }
    Require(Imported(device, destination), "direct release retired the unrelated copy destination");
    Unmap(device, destination);
}
}

int main(int argc, char** argv) {
    try {
        Require(argc <= 2, "expected mappings, heap, locked, copy or direct test mode");
        auto device = OpenDevice();
        if (!device) return VulkanTestSkipped;
        const std::string_view mode = argc == 2 ? argv[1] : "mappings";
        if (mode == "mappings") CheckMappings(*device);
        else if (mode == "heap") CheckHeap(*device);
        else if (mode == "locked") CheckLockedMutation(*device);
        else if (mode == "copy") CheckCopy(*device);
        else if (mode == "direct") CheckDirectRelease(*device);
        else throw std::runtime_error("unknown guest memory lifetime test mode");
        Finish(device);
        std::puts("guest memory host import lifetime passed");
        return 0;
    } catch (const std::exception& error) {
        std::fprintf(stderr, "guest memory host import lifetime: %s\n", error.what());
        return 1;
    }
}
