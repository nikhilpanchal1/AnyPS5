#include "GuestMemoryLifetimeSupport.hpp"
using namespace GuestMemoryLifetime;

namespace {
std::unique_ptr<AgcDriver::VulkanDevice> device;
}

extern "C" int APS5_VABI Begin_nid_no_patch() {
    try {
        device = OpenDevice();
        if (device) return 0;
        std::fflush(stdout);
        std::exit(VulkanTestSkipped);
    } catch (const std::exception& error) {
        std::fprintf(stderr, "converted guest Vulkan initialization failed: %s\n", error.what());
        std::exit(1);
    }
}

extern "C" int APS5_VABI Fill_nid_no_patch(void* pointer, int gpu) {
    std::lock_guard lock(GpuMutex());
    if (!Access(pointer, gpu != 0)) {
        std::fputs("converted guest mapping does not match its requested CPU and GPU access\n", stderr);
        return 1;
    }
    return !Fill(*device, pointer);
}

extern "C" int APS5_VABI Retired_nid_no_patch(const void* pointer) {
    const bool imported = Imported(*device, pointer);
    if (imported) std::fputs("converted guest observed a stale Vulkan host import\n", stderr);
    return imported;
}

extern "C" int APS5_VABI Verify_nid_no_patch(const void* pointer, int zero) {
    return !Verify(pointer, zero != 0);
}

extern "C" [[noreturn]] void APS5_VABI Finish_nid_no_patch(int result) {
    Finish(device);
    std::printf("converted guest memory/Vulkan lifetime result=%d\n", result);
    std::fflush(stdout);
    std::exit(result);
}
