#include "prx/libSceAgcDriver/Execution/include/VulkanDevice.hpp"
#include "prx/libSceAgcDriver/Graphics/include/Draw.hpp"
#include "prx/libc/include/GuestAllocations.hpp"
#include "Recompiler.hpp"
#include "Optimization/ResourceProgram.hpp"
#include "VulkanTestDevice.hpp"
#ifdef _WIN32
#ifndef NOMINMAX
#define NOMINMAX
#endif
#include <windows.h>
#endif
#include <algorithm>
#include <array>
#include <cstdint>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <iostream>
#include <span>
#include <string>
#include <string_view>
#include <vector>

namespace {

using AgcDriver::Graphics::Require;
constexpr std::uint32_t Threads = 64u;
constexpr std::uint32_t Records = 4u;
constexpr std::size_t BlockBytes = 65536u;
constexpr std::uint32_t OutputBase = 0x8000u;
constexpr std::uint32_t OutputStride = 64u;
constexpr std::uint32_t Fill = 0xdeadbeefu;
static_assert(OutputBase + Records * Threads * OutputStride <= BlockBytes);

class GuestBlock {
public:
    GuestBlock() {
#ifdef _WIN32
        block = static_cast<std::uint8_t*>(VirtualAlloc(nullptr, BlockBytes, MEM_RESERVE | MEM_COMMIT, PAGE_READWRITE));
#else
        block = static_cast<std::uint8_t*>(std::aligned_alloc(BlockBytes, BlockBytes));
#endif
        Require(block != nullptr, "buffer descriptor anchors: cannot allocate guest memory");
        GuestAllocations::Mutation().Add(block, BlockBytes, true, true, true);
    }

    ~GuestBlock() {
        GuestAllocations::Mutation().Remove(block);
#ifdef _WIN32
        VirtualFree(block, 0, MEM_RELEASE);
#else
        std::free(block);
#endif
    }

    GuestBlock(const GuestBlock&) = delete;
    GuestBlock& operator=(const GuestBlock&) = delete;
    std::uint8_t* Data() { return block; }

private:
    std::uint8_t* block = nullptr;
};

std::array<std::uint32_t, 4> Descriptor(const void* data, std::uint32_t bytes) {
    const auto address = reinterpret_cast<std::uintptr_t>(data);
    return {static_cast<std::uint32_t>(address), static_cast<std::uint32_t>((address >> 32u) & 0xffffu), bytes, 0x31016facu};
}

std::vector<std::uint32_t> Code(bool coherent, bool waterfall) {
    std::vector<std::uint32_t> code{0x34020082u, 0x34040086u};
    if (waterfall) code.insert(code.end(), {0x36060083u, 0xbea0047eu});
    else code.push_back(0xbea80380u);
    const auto loop = code.size();
    if (waterfall) code.insert(code.end(), {0x7e200503u, 0x7d840610u, 0xbea2246au, 0x8f128410u, 0x8f298c10u});
    else code.insert(code.end(), {0x8f128428u, 0x8f298c28u});
    code.insert(code.end(), {0xf4280200u, 0x24000000u, 0xbf8cc07fu});
    const auto glc = coherent ? 0x4000u : 0u;
    code.insert(code.end(), {
        0xe0301000u | glc, 0x80020401u,
        0xe0341004u | glc, 0x80020501u,
        0xe03c100cu | glc, 0x80020701u,
        0xe0381018u | glc, 0x80020a01u,
        0xbf8c3f70u,
        0xe0701000u, 0x29010402u,
        0xe0741004u, 0x29010502u,
        0xe07c100cu, 0x29010702u,
        0xe0781018u, 0x29010a02u
    });
    if (waterfall) {
        code.push_back(0x8afe7e22u);
        code.push_back(0xbf890000u | static_cast<std::uint16_t>(static_cast<int>(loop) - static_cast<int>(code.size() + 1u)));
        code.push_back(0xbefe0420u);
    } else {
        code.insert(code.end(), {0x80288128u, 0xbf0a8428u});
        code.push_back(0xbf850000u | static_cast<std::uint16_t>(static_cast<int>(loop) - static_cast<int>(code.size() + 1u)));
    }
    code.push_back(0xbf810000u);
    return code;
}

struct Record {
    std::uint32_t base;
    std::uint32_t bytes;
};

std::array<Record, Records> RecordSet(std::uint32_t revision) {
    if (revision == 0u) return {{{0x1000u, 512u}, {0x2001u, 265u}, {0x3003u, 128u}, {0u, 0u}}};
    return {{{0x4002u, 257u}, {0x1003u, 512u}, {0u, 0u}, {0x3001u, 193u}}};
}

std::vector<std::uint8_t> Initial(GuestBlock& guest, std::uint32_t revision) {
    std::vector<std::uint8_t> initial(BlockBytes);
    for (std::size_t byte = 0u; byte < initial.size(); ++byte) initial[byte] = static_cast<std::uint8_t>(byte * 41u + (byte >> 8u) * 13u + revision * 97u);
    for (std::uint32_t offset = OutputBase; offset < OutputBase + Records * Threads * OutputStride; offset += 4u) std::memcpy(initial.data() + offset, &Fill, sizeof(Fill));
    const auto records = RecordSet(revision);
    for (std::uint32_t record = 0u; record < Records; ++record) {
        const auto descriptor = Descriptor(records[record].base == 0u ? nullptr : guest.Data() + records[record].base, records[record].bytes);
        std::memcpy(initial.data() + record * sizeof(descriptor), descriptor.data(), sizeof(descriptor));
    }
    return initial;
}

std::vector<std::uint8_t> Expected(const std::vector<std::uint8_t>& initial, std::uint32_t revision, bool waterfall) {
    auto expected = initial;
    const auto records = RecordSet(revision);
    for (std::uint32_t record = 0u; record < Records; ++record) {
        for (std::uint32_t lane = 0u; lane < Threads; ++lane) {
            if (waterfall && lane % Records != record) continue;
            for (std::uint32_t component = 0u; component < 10u; ++component) {
                const auto offset = lane * 4u + component * 4u;
                std::uint32_t value = 0u;
                if (records[record].base != 0u && offset + 4u <= records[record].bytes) std::memcpy(&value, initial.data() + records[record].base + offset, sizeof(value));
                const auto destination = OutputBase + record * Threads * OutputStride + lane * OutputStride + component * 4u;
                std::memcpy(expected.data() + destination, &value, sizeof(value));
            }
        }
    }
    return expected;
}

void Run(AgcDriver::VulkanDevice& device, GuestBlock& guest, std::uint32_t waveSize, const ShaderRecompiler::SpirvTarget& target, bool coherent, bool waterfall, bool requireAnchors, const std::string& mode) {
    std::fprintf(stderr, "buffer descriptor anchors: %s %s%s start\n", mode.c_str(), waterfall ? "waterfall" : "counter", coherent ? " glc" : "");
    const auto code = Code(coherent, waterfall);
    std::array<std::uint32_t, 8> userData{};
    const auto table = Descriptor(guest.Data(), Records * 16u);
    const auto output = Descriptor(guest.Data() + OutputBase, Records * Threads * OutputStride);
    std::copy(table.begin(), table.end(), userData.begin());
    std::copy(output.begin(), output.end(), userData.begin() + 4u);
    const std::array<ShaderRecompiler::MemoryRegion, 1> memory{{{reinterpret_cast<std::uintptr_t>(code.data()), std::as_bytes(std::span(code))}}};
    const ShaderRecompiler::ShaderComputeStageInfo compute{{Threads, 1u, 1u}, 0u, {false, false, false}, false, 1u};
    ShaderRecompiler::RecompileRequest request{
        {ShaderRecompiler::ShaderStage::Compute, reinterpret_cast<std::uintptr_t>(code.data()), code, 0u, {}},
        {waveSize, 0u, userData, compute, std::nullopt, std::nullopt, memory},
        target, {0u, 0u, 0u, 128u}};
    const auto prepared = ShaderRecompiler::PrepareShader(request);
    for (std::uint32_t revision = 0u; revision < 2u; ++revision) {
        const auto initial = Initial(guest, revision);
        std::memcpy(guest.Data(), initial.data(), initial.size());
        ShaderRecompiler::SrtRuntime runtime{};
        runtime.userData = userData;
        const auto capture = ShaderRecompiler::CaptureResources(request, runtime, *prepared);
        const auto result = ShaderRecompiler::MaterializeShader(request, *capture, *prepared);
        std::fprintf(stderr, "buffer descriptor anchors: %s revision %u materialized\n", mode.c_str(), revision);
        if (requireAnchors) {
            const std::string_view module(reinterpret_cast<const char*>(result->spirv.data()), result->spirv.size() * sizeof(std::uint32_t));
            Require(module.find("bda_anchor_range") != std::string_view::npos, "runtime buffer descriptor loads did not share a BDA anchor");
        }
        device.Dispatch(*result, 1u, 1u, 1u, {}, reinterpret_cast<std::uintptr_t>(code.data()));
        device.WaitIdle();
        const auto expected = Expected(initial, revision, waterfall);
        for (std::size_t byte = 0u; byte < expected.size(); ++byte) {
            Require(guest.Data()[byte] == expected[byte], "buffer descriptor anchors: " + mode + (coherent ? " glc" : "") + (waterfall ? " waterfall" : " counter") + " revision " + std::to_string(revision) + " byte " + std::to_string(byte) + " is " + std::to_string(guest.Data()[byte]) + ", expected " + std::to_string(expected[byte]));
        }
        std::fprintf(stderr, "buffer descriptor anchors: %s revision %u passed\n", mode.c_str(), revision);
    }
}

}

int main(int argc, char** argv) {
    try {
        bool requireAnchors = false;
        bool coherent = false;
        bool waterfall = false;
        bool splitMode = false;
        std::uint32_t waveSize = 32u;
        for (int argument = 1; argument < argc; ++argument) {
            const std::string_view value(argv[argument]);
            if (value == "--require-anchors") requireAnchors = true;
            else if (value == "--counter32") { waveSize = 32u; waterfall = false; }
            else if (value == "--counter64") { waveSize = 64u; waterfall = false; }
            else if (value == "--waterfall32") { waveSize = 32u; waterfall = true; }
            else if (value == "--waterfall64") { waveSize = 64u; waterfall = true; }
            else if (value == "--coherent") coherent = true;
            else if (value == "--split") splitMode = true;
            else Require(false, "unknown buffer descriptor anchor test argument");
        }
        const auto device = OpenVulkanTestDevice();
        if (!device) return VulkanTestSkipped;
        GuestBlock guest;
        const auto native = device->Target();
        const auto split = device->ComputeTarget(32u);
        if (splitMode && split.subgroupSize == native.subgroupSize) {
            std::puts("skipped, device has no distinct 32-lane subgroup target");
            return VulkanTestSkipped;
        }
        Require(!splitMode || waveSize == 64u, "split target requires a wave64 test");
        Run(*device, guest, waveSize, splitMode ? split : native, coherent, waterfall, requireAnchors, "wave" + std::to_string(waveSize) + (splitMode ? " split" : ""));
        std::puts("runtime buffer descriptor anchors, counted and waterfall loops, recapture, nulls, bounds and guards pass");
        return 0;
    } catch (const std::exception& error) {
        std::cerr << error.what() << '\n';
        return 1;
    }
}
