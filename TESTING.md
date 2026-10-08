# AnyPS5 testing reference

Updated: 2026-10-08. A reusable test pathway and an index of verified lessons.
Check the current workflows, available targets and environment before using a
recipe. Test names and counts vary by revision.
The recipes capture checks that have worked here. Use them as a foundation and
actively look for stronger ways to test each change whenever the environment
allows. A green checklist alone does not establish adequate coverage.

## 1. Establish the environment and the failure

In the prepared Linux cloud environment:

```bash
cd /workspace/AnyPS5
source /workspace/.anyps5/activate.sh
cmake --version
ninja --version
ccache --version
vulkaninfo --summary
```

Read `/workspace/.anyps5/start.md` first. These paths describe the prepared image;
a fresh image may need different setup. Record the OS, compiler, Vulkan driver
and device, source revision, build flags and relevant environment overrides.
Never print credentials or disable TLS, signatures, assertions or validation.

Run the smallest reproduction on the baseline. For a bug fix, demonstrate that
the relevant regression fails before the fix and passes afterward. Identify the
expected failure; a crash from broken setup is not useful baseline evidence.
Compare identical fixtures, configuration and driver.

Use a separate baseline build or standalone probe when practical. If a baseline
comparison temporarily changes source, preserve local changes, restore the exact
source, and rebuild it before final verification. Keep logs under a task-specific
directory outside the checkout, for example `/workspace/work/validation/<issue>/`.

## 2. Choose the checks that prove the behavior

| Change area | Useful pathway | Evidence to inspect |
| --- | --- | --- |
| Shader optimizer/compiler | Assemble or compile a fixture; validate input/output; exercise relevant modes and capabilities | Legal instructions, expected conversions, preserved stores/bindings and unaffected folding |
| GPU memory/execution | Compile a guest fixture; submit through the real driver; synchronize; read back results | Actual bytes or values, relevant wave modes and device selection |
| Relinker/guest runtime | Convert and run a small guest fixture through the real loader/runtime | Exit status, output, imports, relocations and error paths |
| Parsing or memory safety | Valid boundaries, malformed inputs, truncation and byte-order cases where supported; focused sanitizers | Correct rejection and diagnostics, no out-of-bounds access or hangs |
| Platform or optional feature | Relevant enabled/disabled builds and a matching platform runner | Configuration-specific behavior and unchanged supported paths |
| Performance | Same input, device and configuration; repeat measurements | Timing and output equivalence, including any changed costs |

Prefer observable results over tests that mirror the implementation or only
check exported symbols. For an internal guard that validation normally prevents
reaching, public malformed-input tests prove rejection ordering; a direct,
temporary helper harness can check the guard itself. Keep the distinction clear.

### Explore beyond the existing recipes

Ask what could still be wrong even if every listed test passes. Identify the
important untested behavior and design additional checks that could expose it:

- Probe boundary values, sizes, alignment, aliases, malformed inputs and failure
  paths relevant to the change.
- Vary feature combinations, optimizer modes, cache state and supported devices
  or targets. Check interactions with nearby code and callers.
- Use deterministic randomized inputs or compare against an independent reference
  when those methods can catch mistakes that fixed fixtures miss.
- Exercise realistic workloads and, where relevant, concurrency, resource cleanup,
  repeated operations and performance. Inspect actual results and diagnostics.
- Explore the available tools: a small guest program, direct helper harness,
  sanitizers, tracing or device readback may provide evidence the suite lacks.

For each extra check, state what failure it could detect. Prioritize consequential
unknowns over repeating checks that already answer the same question. Address
surprising results before wrapping up. If a useful check is unavailable, record
the gap and why it matters. When the behavior and important risks are covered,
report the evidence and remaining limits; avoid claims of exhaustive testing.
Carry useful new methods and discoveries into this reference.

## 3. Configure and build

Prepared-image Release configuration:

```bash
cmake -S . -B build -G Ninja \
  -DCMAKE_BUILD_TYPE=Release -DBUILD_TESTING=ON \
  -DCMAKE_C_COMPILER=gcc -DCMAKE_CXX_COMPILER=g++ \
  -DCMAKE_C_COMPILER_LAUNCHER=ccache -DCMAKE_CXX_COMPILER_LAUNCHER=ccache \
  -DCMAKE_PREFIX_PATH=/workspace/.anyps5/sysroot/usr \
  -DCMAKE_EXPORT_COMPILE_COMMANDS=ON \
  -DCMAKE_TLS_VERIFY=ON -DCMAKE_TLS_CAINFO="$SSL_CERT_FILE"
cmake --build build --parallel 4
cmake --build build --target libs --parallel 4
```

Use `-DANYPS5_ENABLE_SPIRV_TOOLS=ON` for optimizer work; its default is OFF.
Verify both ON and OFF when the change affects that boundary. Rebuild after each
configuration change, and record the configuration used for every test run.
Do not let parallel workers reconfigure or mutate a shared build directory.

## 4. Focused checks, modes and caches

Discover the test names with `ctest --test-dir build -N`. Select the relevant
tests with an anchored regex, and use `--no-tests=error` to catch empty selections.
A short environment smoke test, where these names are registered:

```bash
ANYPS5_REQUIRE_VULKAN=1 GALLIUM_OVERRIDE_CPU_CAPS=avx \
  ctest --test-dir build --output-on-failure --no-tests=error --timeout 120 \
  -R '^(amd64_only_converter|input_magic|string_table_bounds|guest_png_dec|guest_jpeg_dec|agc_driver_buffer_load_store)$'
```

Optimizer-related regressions may register default, full and none variants.
Their wrappers select `APS5_SPIRV_OPT` separately. When invoking a binary directly,
use a separate process per mode; the optimizer caches its environment choice.

Example cold-cache regression family introduced by PR #1343. Use only on a
revision where these names exist, with SPIRV-Tools ON:

```bash
ANYPS5_REQUIRE_VULKAN=1 GALLIUM_OVERRIDE_CPU_CAPS=avx \
  ANYPS5_NO_SHADER_CACHE=1 MESA_SHADER_CACHE_DISABLE=true \
  ctest --test-dir build --output-on-failure --no-tests=error --timeout 120 \
  --repeat until-fail:3 \
  -R '^agc_(spirv_(narrow_constant_store|optimizer)|driver_constant_store)(_full|_none)?$'
```

SPIR-V header/version regressions do not require a Vulkan device. With
SPIRV-Tools enabled, run both byte orders, legal versions, requested limits and
malformed inputs in the three isolated optimizer modes:

```bash
ctest --test-dir build --output-on-failure --no-tests=error --timeout 120 \
  --repeat until-fail:3 -R '^agc_spirv_version(_full|_none)?$'
```

These tests independently validate fixtures and optimized output, check that
inputs remain unchanged and require exact word preservation in `none` mode.
They do not establish shader execution or vendor GPU behavior.

Require Vulkan so an unavailable device fails the GPU run. Disable the emulator
and Mesa caches when proving the changed compilation/execution path. Cold-cache
testing does not replace warm-cache behavior checks for a cache-related change.

For focused memory-safety checks, compile the changed code with
`-fsanitize=address,undefined -fno-omit-frame-pointer` and run with
`ASAN_OPTIONS=detect_leaks=1:halt_on_error=1` and
`UBSAN_OPTIONS=halt_on_error=1`. State which code was instrumented; a sanitized
harness linked to uninstrumented dependencies does not cover those dependencies.

If LeakSanitizer reports that it cannot run under ptrace, record leak coverage
as unavailable. Run the remaining ASan/UBSan checks with
`ASAN_OPTIONS=detect_leaks=0:halt_on_error=1`; this does not establish leak safety.
The restricted runtime used on 2026-10-08 had this tracing limitation.

## 5. Final CI and contribution checks

After focused checks, use the Linux build workflow's full sequence: configure,
build, build `libs`, then repeat CTest three times:

```bash
ANYPS5_REQUIRE_VULKAN=1 GALLIUM_OVERRIDE_CPU_CAPS=avx \
  ctest --test-dir build --output-on-failure --no-tests=error \
  --timeout 120 --repeat until-fail:3
```

Count distinct passing tests separately from repeated executions. Record skips
by reason and investigate new failures or skips. A skipped regression does not
prove the fix. Run applicable platform checks; Linux results do not establish
Windows behavior, and software Vulkan does not establish vendor hardware behavior.

Before pushing committed changes, check the full branch and draft PR text.
Use the current upstream base. These commands assume an `upstream` remote;
replace the title and body path with the actual draft:

```bash
git diff --check
git diff --check upstream/main...HEAD
python3 tools/check_conventions.py --base upstream/main --head HEAD \
  --title '<Conventional Commit PR title>' --body /path/outside/repo/pr-body.md
if [ -n "$(git diff --name-only upstream/main...HEAD -- ':(glob)**/CONTRIBUTION_GUIDE.md' ':(glob)**/TESTING.md')" ]; then
  printf '%s\n' 'Fork notes are present in the contribution diff.' >&2
  exit 1
fi
```

The checker inspects committed history, so verify uncommitted work separately.
Also run other applicable PR workflows, such as progress reporting when relevant.
Record the exact tested revision; for a dirty tree, identify the tested patch.
After new code changes, rerun affected checks. Retest after a rebase if the
combined code or assumptions changed. Report only results actually observed.

## 6. Verified lessons to carry forward

Evidence checked on 2026-10-08:

| Finding | Practical use | Limits and evidence |
| --- | --- | --- |
| Mesa 26.1.6 llvmpipe works in the prepared image; 25.0.7 failed an existing color-comparison test | Inspect the selected ICD/driver before blaming a GPU failure on the patch | This image; see `/workspace/.anyps5/start.md` |
| This runtime returns ENOSYS for userfaultfd; llvmpipe subgroups have eight lanes | Report write-tracking and unsupported subgroup skips separately | They do not cover those paths; the last full run had 23 skips, not a permanent expected count |
| Optimizer validation plus real GPU readback caught the narrow-constant bug | Pair compiler-level checks with execution when shader behavior changes | [PR #1343](https://github.com/boykopovar/AnyPS5/pull/1343); local Linux ON/OFF suites and cold regressions passed three times |
| The restricted sandbox denied TCP/UDP socket creation with EPERM | Compare failures with a direct host socket probe before attributing them to a source change | Locally verified on 2026-10-08; guest net, UDP, poll and TCP tests failed, and guest filesystem also required a UDP socket. No permission or proxy changes were needed for diagnosis |
| The raw SPIR-V version guard rejected valid byte-swapped 1.3 modules | Check both byte orders, stricter requested limits, diagnostic ordering and input preservation in every optimizer mode | Locally verified against the original optimizer and the fix; SPIR-V 1.0–1.6 fixtures, eight Vulkan/SPIR-V targets, ASan/UBSan on the wrapper/harness. [Version-validation commit](https://github.com/nikhilpanchal1/AnyPS5/commit/c2dad207adf27bcf7bf66cbe359c7c4af99d2b35) |
| Windows/NVIDIA tests independently confirmed the same fix | Match the tested revision and attribute external evidence | [Windows report](https://github.com/boykopovar/AnyPS5/pull/1343#issuecomment-6050894615): 413 passes; nine cold regressions repeated three times. External report, not a local Windows run |
| Windows documentation-link checking used host path separators | Diagnose the checker failure separately from source behavior | [PR #1254](https://github.com/boykopovar/AnyPS5/pull/1254). Check whether it has landed; do not silently patch the checker to claim a standard pass |
| A physical NVIDIA validation run needed an existing write-watch override | Check device/memory-import setup when SPIR-V-only tests pass but GPU submission fails | [Linux/NVIDIA report](https://github.com/boykopovar/AnyPS5/pull/1343#pullrequestreview-5449893004) used `APS5_WRITE_WATCH_IMPORTS=watch`; platform-specific, related to #1329 |
| An overlap-bot warning can identify shared CMake/doc edits | Inspect the actual overlap and current mergeability before declaring a dependency | Use the current PRs and diffs; shared insertion points alone do not prove duplicate functionality |

The unchanged `agc_driver_flat_store` fixture exceeded the 120-second limit
with SPIRV-Tools ON and OFF on the prepared llvmpipe image at `a5df1a87`.
The original optimizer also timed out at `7fccb7ff`. Compare the same fixture,
cache state and device before attributing this timeout to an optimizer patch;
[#1171](https://github.com/boykopovar/AnyPS5/pull/1171) investigates a smaller
fixture. These are host-specific observations, not an expected failure on every
platform.

## 7. Add or revise a lesson

Keep reusable findings here and full logs in the issue/PR or task artifacts.
Use this compact format when adding a new pathway:

- **Date / area:** what subsystem or environment this applies to.
- **Status / evidence:** locally verified, externally reported, or a hypothesis;
  source revision, device/configuration and a durable evidence link.
- **Recipe / expected result:** minimal runnable commands and observable output.
- **Coverage / limits:** what passed, failed or skipped and what remains untested.
- **Follow-up:** when to recheck; replace superseded advice rather than accumulating
  conflicting instructions.

Promote a hypothesis to recommended practice only after verification. Update
the index and useful commands on the fork's `contribution-notes` branch after each
investigation. Fetch and reconcile concurrent edits before pushing that branch.
