#ifndef CORE_LIBS_PRX_LIBSCEAGCDRIVER_TESTS_GUESTMEMORYLIFETIMESUPPORT_HPP
#define CORE_LIBS_PRX_LIBSCEAGCDRIVER_TESTS_GUESTMEMORYLIFETIMESUPPORT_HPP

#include "prx/libSceAgcDriver/tests/execution/VulkanTestDevice.hpp"
#include "prx/libSceAgcDriver/Execution/include/GuestMemory.hpp"
#include "prx/libSceAgcDriver/Graphics/include/GuestBufferMemory.hpp"
#include "prx/libSceAgcDriver/Graphics/include/Recorder.hpp"
#include "prx/libc/include/GuestAllocations.hpp"
#include "prx/libc/include/general/VabiMacros.hpp"
#include <SDL_error.h>
#include <SDL_loadso.h>
#include <array>
#include <cstring>
#include <mutex>
#include <string>

namespace GuestMemoryLifetime {
using AgcDriver::GuestMemory::GpuMutex;
using AgcDriver::Graphics::Require;
constexpr std::size_t BlockBytes = 65536, FillBytes = 4096;
constexpr std::array<std::uint32_t, 4> Pattern{0x12345678u, 0x89abcdefu, 0x24681357u, 0xfedcba98u};

static auto OpenDevice() {
    auto device = OpenVulkanTestDevice();
    if (!device) return device;
    if (std::getenv("APS5_NO_HOST_IMPORT") != nullptr) {
        std::puts("skipped, host imports are disabled by APS5_NO_HOST_IMPORT");
        return decltype(device){};
    }
#ifdef _WIN32
    constexpr const char* libraryName = "vulkan-1.dll";
#else
    constexpr const char* libraryName = "libvulkan.so.1";
#endif
    const std::unique_ptr<void, decltype(&SDL_UnloadObject)> library(SDL_LoadObject(libraryName), &SDL_UnloadObject);
    Require(library != nullptr, std::string("cannot load Vulkan for the host import capability query: ") + SDL_GetError());
    const auto resolve = reinterpret_cast<PFN_vkGetDeviceProcAddr>(SDL_LoadFunction(library.get(), "vkGetDeviceProcAddr"));
    Require(resolve != nullptr, std::string("cannot resolve vkGetDeviceProcAddr for the host import capability query: ") + SDL_GetError());
    if (resolve(device->Device(), "vkGetMemoryHostPointerPropertiesEXT") != nullptr) return device;
    std::puts("skipped, the device has no VK_EXT_external_memory_host");
    return decltype(device){};
}

static std::uint64_t Address(const void* pointer) {
    return reinterpret_cast<std::uintptr_t>(pointer);
}

static bool Imported(const AgcDriver::VulkanDevice& device, const void* pointer, std::size_t bytes = BlockBytes) {
    AgcDriver::Graphics::Context probe{};
    probe.device = device.Device();
    probe.hostImportAlignment = 1;
    return AgcDriver::Graphics::HostImportCovers(probe, Address(pointer), bytes);
}

static bool Access(const void* pointer, bool gpu) {
    GuestAllocations::Mutation mutation;
    const auto range = mutation.Find(pointer);
    return range.readable && range.writable && range.gpu == gpu;
}

static bool Verify(const void* pointer, bool zero = false, std::size_t bytes = FillBytes) {
    const auto* data = static_cast<const std::uint8_t*>(pointer);
    const auto* pattern = reinterpret_cast<const std::uint8_t*>(Pattern.data());
    for (std::size_t offset = 0; offset < bytes; ++offset) {
        const auto expected = zero ? std::uint8_t{0} : pattern[offset % sizeof(Pattern)];
        if (data[offset] != expected) {
            std::fprintf(stderr, "guest memory mismatch at byte %zu: expected %u, observed %u\n", offset, unsigned(expected), unsigned(data[offset]));
            return false;
        }
    }
    return true;
}

static bool Fill(AgcDriver::VulkanDevice& device, void* pointer, std::size_t importBytes = BlockBytes) {
    std::lock_guard lock(GpuMutex());
    return device.FillBuffer(Address(pointer), FillBytes, Pattern) && Imported(device, pointer, importBytes);
}

static void Finish(std::unique_ptr<AgcDriver::VulkanDevice>& device) {
    {
        std::lock_guard lock(GpuMutex());
        device->WaitIdle();
    }
    device.reset();
}
}
#endif
