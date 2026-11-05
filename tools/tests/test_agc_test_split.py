import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import agc_test_split

TOOL = Path(__file__).resolve().parents[1] / "agc_test_split.py"
LISTS = agc_test_split.LISTS
EXECUTION = ["agc_driver_image_tests"]
FRAGMENTS = agc_test_split.FRAGMENTS

ALPHA = """    add_test_executable(agc_alpha_tests tests/Alpha.cpp)
    target_link_libraries(agc_alpha_tests PRIVATE libc)
    add_test(NAME agc_alpha COMMAND agc_alpha_tests)
    set_tests_properties(agc_alpha PROPERTIES TIMEOUT 20)
"""
BETA = """    add_test_executable(agc_beta_tests tests/Beta.cpp)
    foreach(mode IN ITEMS one two)
        add_test(NAME agc_beta_${mode} COMMAND agc_beta_tests ${mode})
    endforeach()
    if(WIN32)
        set_tests_properties(agc_beta_one agc_beta_two PROPERTIES TIMEOUT 40)
    endif()
"""
DELTA = """    add_test_executable(agc_delta_tests tests/Delta.cpp)
    add_test(NAME agc_delta COMMAND agc_delta_tests)
"""


def original(blocks=(ALPHA, BETA), items="agc_gamma_tests", tweaks="", image=True, library="Export.cpp"):
    image_case = ("        if(agcTestName STREQUAL \"agc_driver_image\")\n"
                  "            set_tests_properties(${agcTestName} PROPERTIES TIMEOUT 30)\n"
                  "        endif()\n") if image else ""
    image_tweak = "    set_tests_properties(agc_driver_image PROPERTIES SKIP_RETURN_CODE 77)\n" if image else ""
    return (f"add_library(libSceAgcDriver SHARED EXCLUDE_FROM_ALL {library})\n\n"
            "if(BUILD_TESTING)\n" + "\n".join(blocks) + "endif()\n\n"
            "add_test_executable(agc_gamma_tests EXCLUDE_FROM_ALL tests/Gamma.cpp)\n"
            "target_link_libraries(agc_gamma_tests PRIVATE libc)\n\n"
            "file(GLOB agcExecutionTestSources CONFIGURE_DEPENDS ${CMAKE_CURRENT_SOURCE_DIR}/tests/execution/*.cpp)\n"
            "set(agcExecutionTests)\n"
            "foreach(agcExecutionTestSource IN LISTS agcExecutionTestSources)\n"
            "    get_filename_component(agcExecutionTestName ${agcExecutionTestSource} NAME_WE)\n"
            "    string(TOLOWER \"agc_driver_${agcExecutionTestName}_tests\" agcExecutionTest)\n"
            "    add_test_executable(${agcExecutionTest} EXCLUDE_FROM_ALL ${agcExecutionTestSource})\n"
            "    list(APPEND agcExecutionTests ${agcExecutionTest})\n"
            "endforeach()\n"
            "if(BUILD_TESTING)\n"
            f"    foreach(agcTest IN ITEMS {items} ${{agcExecutionTests}})\n"
            "        if(agcTest STREQUAL \"agc_driver_skipped_tests\")\n"
            "            continue()\n"
            "        endif()\n"
            "        string(REGEX REPLACE \"_tests$\" \"\" agcTestName \"${agcTest}\")\n"
            "        set_target_properties(${agcTest} PROPERTIES EXCLUDE_FROM_ALL OFF)\n"
            "        add_test(NAME ${agcTestName} COMMAND ${agcTest})\n" + image_case +
            "    endforeach()\n" + image_tweak + tweaks +
            "endif()\n\n"
            "if(BUILD_TESTING)\n"
            "    get_directory_property(agcRegisteredTests TESTS)\n"
            "    set_property(TEST ${agcRegisteredTests} APPEND PROPERTY ENVIRONMENT \"X=1\")\n"
            "endif()\n")


class SplitTextTests(unittest.TestCase):
    def test_refactor_registers_default_tests_through_a_function(self):
        text = agc_test_split.refactor(original())
        self.assertIn("function(agc_add_default_test agcTest)", text)
        self.assertIn("    agc_add_default_test(agc_gamma_tests)\n", text)
        self.assertIn("    set_tests_properties(agc_driver_image PROPERTIES TIMEOUT 30)\n", text)
        self.assertIn("        agc_add_default_test(${agcTest})\n", text)
        self.assertNotIn("${agcExecutionTests})", text)
        self.assertLess(text.index("function(agc_add_default_test"), text.index("agc_add_default_test(agc_gamma_tests)"))
        self.assertEqual(agc_test_split.refactor(text), text)

    def test_split_writes_one_fragment_per_test_executable(self):
        lists, fragments = agc_test_split.migrated(original(), EXECUTION)
        self.assertEqual(sorted(fragments), ["agc_alpha_tests", "agc_beta_tests", "agc_driver_image_tests", "agc_gamma_tests"])
        self.assertEqual(fragments["agc_alpha_tests"], "if(BUILD_TESTING)\n" + ALPHA + "endif()\n")
        self.assertEqual(fragments["agc_beta_tests"], "if(BUILD_TESTING)\n" + BETA + "endif()\n")
        self.assertEqual(fragments["agc_driver_image_tests"],
                         "if(BUILD_TESTING)\n    set_tests_properties(agc_driver_image PROPERTIES TIMEOUT 30)\n"
                         "    set_tests_properties(agc_driver_image PROPERTIES SKIP_RETURN_CODE 77)\nendif()\n")
        self.assertIn("agc_add_default_test(agc_gamma_tests)", fragments["agc_gamma_tests"])
        self.assertNotIn("agc_alpha", lists)
        include = lists.index(agc_test_split.INCLUDE[0])
        self.assertLess(lists.index("agc_add_default_test(${agcTest})"), include)
        self.assertLess(include, lists.index("get_directory_property(agcRegisteredTests TESTS)"))

    def test_split_keeps_a_loop_over_several_executables(self):
        tweaks = ("    foreach(agcTest IN ITEMS agc_alpha_tests agc_gamma_tests)\n"
                  "        set_target_properties(${agcTest} PROPERTIES FOLDER tests)\n"
                  "    endforeach()\n")
        lists, fragments = agc_test_split.migrated(original(tweaks=tweaks), EXECUTION)
        self.assertIn("foreach(agcTest IN ITEMS agc_alpha_tests agc_gamma_tests)", lists)
        self.assertLess(lists.index(agc_test_split.INCLUDE[0]), lists.index("foreach(agcTest IN ITEMS agc_alpha_tests"))

    def test_split_moves_a_loop_over_computed_test_names_with_their_executable(self):
        pattern = ("    foreach(betaCase IN ITEMS one:1 two:2)\n"
                   "        string(REGEX REPLACE \"^([a-z]+):.*$\" \"\\\\1\" betaName \"${betaCase}\")\n"
                   "        set_tests_properties(agc_beta_${betaName} PROPERTIES LABELS beta)\n"
                   "    endforeach()\n")
        lists, fragments = agc_test_split.migrated(original(blocks=(ALPHA, BETA, pattern)), EXECUTION)
        self.assertIn("agc_beta_${betaName}", fragments["agc_beta_tests"])
        self.assertNotIn("agc_beta_${betaName}", lists)

    def test_split_moves_a_loop_that_sets_properties_on_the_tests_it_adds(self):
        state = ("    add_test_executable(agc_beta_state_tests tests/BetaState.cpp)\n"
                 "    set(betaModes three four)\n"
                 "    foreach(mode IN LISTS betaModes)\n"
                 "        add_test(NAME agc_beta_${mode} COMMAND agc_beta_state_tests ${mode})\n"
                 "        set_tests_properties(agc_beta_${mode} PROPERTIES TIMEOUT 9)\n"
                 "    endforeach()\n")
        lists, fragments = agc_test_split.migrated(original(blocks=(ALPHA, BETA, state)), EXECUTION)
        self.assertIn("set_tests_properties(agc_beta_${mode} PROPERTIES TIMEOUT 9)", fragments["agc_beta_state_tests"])
        self.assertNotIn("betaModes", lists)

    def test_split_refuses_a_computed_test_name_several_executables_match(self):
        pattern = ("    foreach(agcCase IN ITEMS alpha beta_one)\n"
                   "        set_tests_properties(agc_${agcCase} PROPERTIES LABELS agc)\n"
                   "    endforeach()\n")
        with self.assertRaises(agc_test_split.SplitError):
            agc_test_split.migrated(original(blocks=(ALPHA, BETA, pattern)), EXECUTION)

    def test_split_refuses_when_no_single_place_fits(self):
        text = original().replace("add_library(libSceAgcDriver SHARED EXCLUDE_FROM_ALL Export.cpp)\n",
                                  "add_library(libSceAgcDriver SHARED EXCLUDE_FROM_ALL Export.cpp)\n"
                                  "add_dependencies(libSceAgcDriver agc_alpha_tests)\n")
        text = text.replace("add_test_executable(agc_alpha_tests tests/Alpha.cpp)",
                            "add_test_executable(agc_alpha_tests tests/Alpha.cpp ${agcLateSource})")
        text = text.replace("if(BUILD_TESTING)\n    get_directory_property",
                            "set(agcLateSource Late.cpp)\nif(BUILD_TESTING)\n    get_directory_property")
        with self.assertRaises(agc_test_split.SplitError):
            agc_test_split.migrated(text, EXECUTION)


class ArgumentTests(unittest.TestCase):
    def test_bracket_comment_ends_at_its_closing_bracket(self):
        text = "set(A #[[c]]x)\n"
        arguments, end, _ = agc_test_split.arguments_of(text, text.index("(") + 1, 0)
        self.assertEqual(arguments, ["A", "x"])
        self.assertEqual(end, len(text) - 1)


class ResolveTests(unittest.TestCase):
    def setUp(self):
        self.root = Path(tempfile.mkdtemp())
        self.git("init", "-q", "-b", "main")
        self.write(LISTS, original())
        self.write(agc_test_split.EXECUTION + "/Image.cpp", "")
        self.commit("build: register tests")

    def tearDown(self):
        shutil.rmtree(self.root, ignore_errors=True)

    def git(self, *args, check=True):
        return subprocess.run(["git", "-c", "user.name=Split Test", "-c", "user.email=test@example.com", "-c", "commit.gpgsign=false",
                               "-c", "core.editor=true", *args], cwd=self.root, capture_output=True, text=True, check=check)

    def write(self, path, text):
        (self.root / path).parent.mkdir(parents=True, exist_ok=True)
        (self.root / path).write_text(text, encoding="utf-8")

    def read(self, path):
        return (self.root / path).read_text(encoding="utf-8")

    def tool(self, command):
        return subprocess.run([sys.executable, str(TOOL), command], cwd=self.root, capture_output=True, text=True, timeout=60)

    def commit(self, message):
        self.git("add", "-A")
        self.git("commit", "-qm", message)

    def rebase(self, change, after_split=None, delete=()):
        self.git("checkout", "-qb", "change")
        self.write(LISTS, change)
        for path in delete:
            (self.root / path).unlink()
        self.commit("test(agc): change tests")
        self.git("checkout", "-q", "main")
        result = self.tool("split")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.commit("build(agc): split test registrations")
        if after_split:
            after_split()
            self.commit("test(agc): change a fragment")
        self.git("checkout", "-q", "change")
        self.assertNotEqual(self.git("rebase", "main", check=False).returncode, 0)
        return self.tool("resolve")

    def test_resolve_moves_a_new_test_executable_into_its_own_fragment(self):
        result = self.rebase(original(blocks=(ALPHA, BETA, DELTA)))
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual(result.stdout.split(), [LISTS, f"{FRAGMENTS}/agc_delta_tests.cmake"])
        self.assertEqual(self.git("diff", "--name-only", "--diff-filter=U").stdout, "")
        self.git("rebase", "--continue")
        self.assertEqual(self.read(f"{FRAGMENTS}/agc_delta_tests.cmake"), "if(BUILD_TESTING)\n" + DELTA + "endif()\n")
        self.assertEqual(self.read(LISTS), self.git("show", "main:" + LISTS).stdout)

    def test_resolve_applies_an_edit_and_a_default_test_to_their_fragments(self):
        change = original(blocks=(ALPHA.replace("TIMEOUT 20", "TIMEOUT 25"), BETA, DELTA), items="agc_gamma_tests agc_delta_tests")
        result = self.rebase(change)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.git("rebase", "--continue")
        self.assertIn("TIMEOUT 25", self.read(f"{FRAGMENTS}/agc_alpha_tests.cmake"))
        self.assertIn("agc_add_default_test(agc_delta_tests)", self.read(f"{FRAGMENTS}/agc_delta_tests.cmake"))
        self.assertEqual(self.read(LISTS), self.git("show", "main:" + LISTS).stdout)

    def test_resolve_merges_with_a_fragment_changed_after_the_split(self):
        def later():
            path = f"{FRAGMENTS}/agc_alpha_tests.cmake"
            self.write(path, self.read(path).replace("PRIVATE libc", "PRIVATE libc libkernel"))

        result = self.rebase(original(blocks=(ALPHA.replace("TIMEOUT 20", "TIMEOUT 25"), BETA)), later)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        alpha = self.read(f"{FRAGMENTS}/agc_alpha_tests.cmake")
        self.assertIn("PRIVATE libc libkernel", alpha)
        self.assertIn("TIMEOUT 25", alpha)

    def test_resolve_leaves_markers_where_both_sides_changed_a_line(self):
        def later():
            path = f"{FRAGMENTS}/agc_alpha_tests.cmake"
            self.write(path, self.read(path).replace("TIMEOUT 20", "TIMEOUT 60"))

        result = self.rebase(original(blocks=(ALPHA.replace("TIMEOUT 20", "TIMEOUT 25"), BETA)), later)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("agc_alpha_tests.cmake", result.stderr)
        self.assertIn("<<<<<<<", self.read(f"{FRAGMENTS}/agc_alpha_tests.cmake"))

    def test_resolve_removes_the_fragment_of_a_deleted_execution_test(self):
        result = self.rebase(original(image=False), delete=[agc_test_split.EXECUTION + "/Image.cpp"])
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn(f"{FRAGMENTS}/agc_driver_image_tests.cmake", result.stdout.split())
        self.assertEqual(self.git("diff", "--name-only", "--diff-filter=U").stdout, "")
        self.git("rebase", "--continue")
        self.assertFalse((self.root / FRAGMENTS / "agc_driver_image_tests.cmake").exists())
        self.assertNotIn("agc_driver_image", self.read(LISTS))

    def test_resolve_stages_nothing_when_every_file_conflicts(self):
        def later():
            path = f"{FRAGMENTS}/agc_alpha_tests.cmake"
            self.write(path, self.read(path).replace("TIMEOUT 20", "TIMEOUT 60"))
            self.write(LISTS, self.read(LISTS).replace("Export.cpp", "Main.cpp"))

        change = original(blocks=(ALPHA.replace("TIMEOUT 20", "TIMEOUT 25"), BETA), library="Library.cpp")
        result = self.rebase(change, later)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn(LISTS, result.stderr)
        self.assertNotEqual(self.git("ls-files", "-u", "--", LISTS).stdout, "")
        self.assertEqual(self.git("diff", "--cached", "--name-only", "--diff-filter=ACDMR").stdout, "")
        self.assertIn("<<<<<<<", self.read(LISTS))

    def test_resolve_needs_a_conflict(self):
        result = self.tool("resolve")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("not in a three-way conflict", result.stderr)

    def test_split_refuses_a_second_run(self):
        self.assertEqual(self.tool("split").returncode, 0)
        result = self.tool("split")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("already includes", result.stderr)


KERNEL_ALPHA = """    add_test_executable(kernel_alpha_tests tests/Alpha.cpp)
    target_link_libraries(kernel_alpha_tests PRIVATE libkernel libc)
    add_test(NAME kernel_alpha COMMAND kernel_alpha_tests)
    set_tests_properties(kernel_alpha PROPERTIES TIMEOUT 20)
"""
KERNEL_BETA = """    add_test_executable(kernel_beta_tests tests/Beta.cpp)
    add_test(NAME kernel_beta COMMAND kernel_beta_tests)
"""
MTYPEPROTECT = """    add_test_executable(guest_mtypeprotect_tests ${LIBS_INCLUDE_DIR}/tests/GuestMtypeprotect.cpp)
    target_include_directories(guest_mtypeprotect_tests PRIVATE ${LIBS_INCLUDE_DIR})
    target_link_libraries(guest_mtypeprotect_tests PRIVATE libkernel libc)
    configure_windows_unwind(guest_mtypeprotect_tests)
    add_test(NAME guest_mtypeprotect COMMAND guest_mtypeprotect_tests)
    set_tests_properties(guest_mtypeprotect PROPERTIES TIMEOUT 20)
    if(WIN32)
        set_tests_properties(guest_mtypeprotect PROPERTIES ENVIRONMENT_MODIFICATION
            "PATH=path_list_prepend:$<TARGET_FILE_DIR:libkernel>")
    endif()
"""


def kernel_original(blocks=(KERNEL_ALPHA, KERNEL_BETA), library="Export.cpp", prefix=""):
    return (f"add_library(libkernel SHARED EXCLUDE_FROM_ALL {library})\n"
            "target_link_libraries(libkernel PRIVATE libc)\n"
            "target_compile_features(libkernel PRIVATE cxx_std_20)\n"
            "configure_windows_unwind(libkernel)\n"
            "target_include_directories(libkernel PRIVATE include)\n\n"
            "if(BUILD_TESTING)\n" + prefix + "\n".join(blocks) + "endif()\n")


class KernelSplitTests(unittest.TestCase):
    def test_implicit_list_context_reads_require_manual_migration(self):
        commands = ("if(CMAKE_CURRENT_LIST_FILE MATCHES \"/CMakeLists.txt$\")\n" + KERNEL_ALPHA + "endif()\n",
                    "list(LENGTH CMAKE_CURRENT_LIST_DIR context_length)\n" + KERNEL_ALPHA,
                    "foreach(context IN LISTS CMAKE_CURRENT_LIST_DIR)\n" + KERNEL_ALPHA + "endforeach()\n")
        for command in commands:
            with self.subTest(command=command):
                with self.assertRaisesRegex(agc_test_split.SplitError, "list context"):
                    agc_test_split.migrated(kernel_original((command, KERNEL_BETA)), spec=agc_test_split.KERNEL_SPEC)

    def test_escaping_control_flow_requires_manual_migration(self):
        for command in ("return()", "break()", "continue()"):
            with self.subTest(command=command):
                text = kernel_original((KERNEL_ALPHA, "if(UNIX)\n" + command + "\nendif()\n", KERNEL_BETA))
                with self.assertRaisesRegex(agc_test_split.SplitError, "escaping"):
                    agc_test_split.migrated(text, spec=agc_test_split.KERNEL_SPEC)

    def test_return_inside_a_registration_function_preserves_its_scope(self):
        prefix = ("function(register_case target)\nif(FALSE)\nreturn()\nendif()\n"
                  "add_executable(${target} tests/Alpha.cpp)\nendfunction()\n")
        text = kernel_original(("register_case(kernel_alpha_tests)\n", KERNEL_BETA), prefix=prefix)
        lists, fragments = agc_test_split.migrated(text, spec=agc_test_split.KERNEL_SPEC)
        self.assertIn(prefix, lists)
        self.assertIn("register_case(kernel_alpha_tests)", fragments["kernel_alpha_tests"])

    def test_duplicated_conditions_cannot_observe_their_own_registrations_or_writes(self):
        for condition, between in (("NOT TARGET kernel_alpha_tests", ""), ("NOT TEST kernel_alpha", ""),
                                   ("registerCases", "set(registerCases FALSE)\n")):
            with self.subTest(condition=condition):
                block = "if(" + condition + ")\n" + KERNEL_ALPHA + between + KERNEL_BETA + "endif()\n"
                text = kernel_original((block,), prefix="set(registerCases TRUE)\n")
                with self.assertRaisesRegex(agc_test_split.SplitError, "duplicated mutable condition"):
                    agc_test_split.migrated(text, spec=agc_test_split.KERNEL_SPEC)

    def test_local_helper_cannot_mutate_another_target(self):
        for subject in ("kernel_zeta_tests", "${fixture}"):
            with self.subTest(subject=subject):
                prefix = ("function(configure_case target fixture)\n"
                          "target_compile_definitions(" + subject + " PRIVATE SHARED_FIXTURE)\nendfunction()\n")
                text = kernel_original((KERNEL_BETA.replace("beta", "zeta"), KERNEL_ALPHA,
                                        "configure_case(kernel_alpha_tests kernel_zeta_tests)\n"), prefix=prefix)
                with self.assertRaisesRegex(agc_test_split.SplitError, "helper mutates another target or test"):
                    agc_test_split.migrated(text, spec=agc_test_split.KERNEL_SPEC)

    def test_local_helper_can_mutate_its_first_target_parameter(self):
        prefix = ("function(configure_case target fixture)\n"
                  "target_compile_definitions(${target} PRIVATE SHARED_FIXTURE)\n"
                  "target_link_libraries(${target} PRIVATE ${fixture})\nendfunction()\n")
        text = kernel_original((KERNEL_BETA.replace("beta", "zeta"), KERNEL_ALPHA,
                                "configure_case(kernel_alpha_tests kernel_zeta_tests)\n"), prefix=prefix)
        _lists, fragments = agc_test_split.migrated(text, spec=agc_test_split.KERNEL_SPEC)
        self.assertIn("configure_case(kernel_alpha_tests kernel_zeta_tests)", fragments["kernel_alpha_tests"])

    def test_local_helper_cannot_rebind_its_owner_parameter(self):
        for command in ("set(target kernel_zeta_tests)", "string(REPLACE alpha zeta target ${target})",
                        "foreach(target IN ITEMS kernel_zeta_tests)\nendforeach()"):
            with self.subTest(command=command):
                prefix = ("function(configure_case target)\n" + command + "\n"
                          "target_compile_definitions(${target} PRIVATE SHARED_FIXTURE)\nendfunction()\n")
                text = kernel_original((KERNEL_BETA.replace("beta", "zeta"), KERNEL_ALPHA,
                                        "configure_case(kernel_alpha_tests)\n"), prefix=prefix)
                with self.assertRaisesRegex(agc_test_split.SplitError, "helper rebinds its owner parameter"):
                    agc_test_split.migrated(text, spec=agc_test_split.KERNEL_SPEC)

    def test_moved_helper_with_derived_test_names_requires_manual_migration(self):
        prefix = ("function(register_case target)\nadd_test(NAME ${target}_case COMMAND ${target})\nendfunction()\n")
        text = kernel_original((KERNEL_ALPHA, "register_case(kernel_alpha_tests)\n"
                                "set_tests_properties(kernel_alpha_tests_case PROPERTIES TIMEOUT 10)\n", KERNEL_BETA), prefix=prefix)
        with self.assertRaisesRegex(agc_test_split.SplitError, "moved helper creates derived test names"):
            agc_test_split.migrated(text, spec=agc_test_split.KERNEL_SPEC)

    def test_command_presence_conditions_require_manual_migration(self):
        prefix = ("if(COMMAND configure_extra)\n" + KERNEL_ALPHA + "endif()\n"
                  "function(configure_extra target)\ntarget_compile_definitions(${target} PRIVATE EXTRA)\nendfunction()\n")
        with self.assertRaisesRegex(agc_test_split.SplitError, "unsupported if\\(COMMAND\\)"):
            agc_test_split.migrated(kernel_original((KERNEL_BETA,), prefix=prefix), spec=agc_test_split.KERNEL_SPEC)

    def test_only_known_standard_package_finders_are_automatic(self):
        for command in ("find_package(Foo)", "find_package(Python3 COMPONENTS Development QUIET)",
                        "find_package(Threads CONFIG REQUIRED)"):
            with self.subTest(command=command):
                with self.assertRaisesRegex(agc_test_split.SplitError, "unsupported find_package"):
                    agc_test_split.migrated(kernel_original(prefix=command + "\n"), spec=agc_test_split.KERNEL_SPEC)

    def test_standard_package_variable_and_target_conditions_cannot_be_hoisted(self):
        for package, options, conditions in (("Python3", "COMPONENTS Interpreter QUIET", ("Python3_FOUND", "TARGET Python3::Interpreter")),
                                             ("Threads", "REQUIRED", ("Threads_FOUND", "TARGET Threads::Threads"))):
            for condition in conditions:
                with self.subTest(package=package, condition=condition):
                    prefix = "if(" + condition + ")\n" + KERNEL_ALPHA + "endif()\nfind_package(" + package + " " + options + ")\n"
                    with self.assertRaisesRegex(agc_test_split.SplitError, "order"):
                        agc_test_split.migrated(kernel_original((KERNEL_BETA,), prefix=prefix), spec=agc_test_split.KERNEL_SPEC)

    def test_unknown_external_helpers_require_manual_migration(self):
        for helper in (False, True):
            with self.subTest(helper=helper):
                call = "external_configure(kernel_alpha_tests)\n"
                prefix = "function(configure_case target)\nexternal_configure(${target})\nendfunction()\n" if helper else ""
                text = kernel_original((KERNEL_ALPHA, "configure_case(kernel_alpha_tests)\n" if helper else call), prefix=prefix)
                with self.assertRaisesRegex(agc_test_split.SplitError, "unknown command external_configure"):
                    agc_test_split.migrated(text, spec=agc_test_split.KERNEL_SPEC)

    def test_only_summarized_local_helper_definitions_are_automatic(self):
        helper = "function(configure_case target)\ntarget_compile_definitions(${target} PRIVATE EXTRA)\nendfunction()\n"
        for prefix in ("if(TRUE)\n" + helper + "else()\nmessage(STATUS unused)\nendif()\n",
                       "foreach(case IN ITEMS one)\n" + helper + "endforeach()\n"):
            with self.subTest(prefix=prefix):
                text = kernel_original((KERNEL_ALPHA, "configure_case(kernel_alpha_tests)\n", KERNEL_BETA), prefix=prefix)
                with self.assertRaisesRegex(agc_test_split.SplitError, "nested or compound helper definition"):
                    agc_test_split.migrated(text, spec=agc_test_split.KERNEL_SPEC)

    def test_filesystem_observation_requires_manual_migration(self):
        for command in ("file(READ source.txt source)", "file(STRINGS source.txt sources)", "file(SHA256 source.txt digest)",
                        "file(GLOB sources *.cpp)", "if(EXISTS marker)\nmessage(STATUS exists)\nendif()",
                        "if(IS_DIRECTORY directory)\nmessage(STATUS directory)\nendif()"):
            with self.subTest(command=command):
                with self.assertRaisesRegex(agc_test_split.SplitError, "unsupported .* effects require a manual migration"):
                    agc_test_split.migrated(kernel_original(prefix=command + "\n"), spec=agc_test_split.KERNEL_SPEC)

    def test_computed_variable_reads_require_manual_migration_in_helpers_too(self):
        for source in ("${${selector}}", "${source_${selector}}", "$ENV{${selector}}", "$CACHE{${selector}}"):
            for helper in (False, True):
                with self.subTest(source=source, helper=helper):
                    prefix = ("set(selector shared_source)\n"
                              "set(shared_source Zeta.cpp)\n")
                    if helper:
                        prefix = ("function(add_kernel_case target)\n"
                                  "add_executable(${target} " + source + ")\n"
                                  "endfunction()\n" + prefix)
                        zeta = "add_kernel_case(kernel_zeta_tests)\n"
                        alpha = "add_kernel_case(kernel_alpha_tests)\n"
                    else:
                        zeta = "add_test_executable(kernel_zeta_tests " + source + ")\n"
                        alpha = "add_test_executable(kernel_alpha_tests " + source + ")\n"
                    text = prefix + "if(BUILD_TESTING)\n" + zeta + "set(shared_source Alpha.cpp)\n" + alpha + "endif()\n"
                    with self.assertRaisesRegex(agc_test_split.SplitError, "computed variable reference"):
                        agc_test_split.migrated(text, spec=agc_test_split.KERNEL_SPEC)

    def test_list_context_is_rejected_in_direct_registrations_and_shared_helpers(self):
        for variable in ("CMAKE_CURRENT_LIST_DIR", "CMAKE_CURRENT_LIST_FILE", "CMAKE_CURRENT_LIST_LINE", "CMAKE_PARENT_LIST_FILE"):
            for helper in (False, True):
                with self.subTest(variable=variable, helper=helper):
                    source = "${" + variable + "}/Alpha.cpp"
                    if helper:
                        text = ("function(add_kernel_case target)\n"
                                "    add_executable(${target} " + source + ")\n"
                                "endfunction()\n"
                                "if(BUILD_TESTING)\n"
                                "    add_kernel_case(kernel_alpha_tests)\n"
                                "    add_test(NAME kernel_alpha COMMAND kernel_alpha_tests)\n"
                                "endif()\n")
                    else:
                        text = kernel_original((KERNEL_ALPHA.replace("tests/Alpha.cpp", source),))
                    with self.assertRaisesRegex(agc_test_split.SplitError, "list context"):
                        agc_test_split.migrated(text, spec=agc_test_split.KERNEL_SPEC)

    def test_target_and_local_variable_conditions_cannot_be_reordered(self):
        zeta = KERNEL_BETA.replace("beta", "zeta")
        for condition, before, after in (("TARGET kernel_zeta_tests", "", ""),
                                          ("wantAlpha", "set(wantAlpha TRUE)\n", "set(wantAlpha FALSE)\n")):
            with self.subTest(condition=condition):
                text = ("if(BUILD_TESTING)\n" + before + zeta + "if(" + condition + ")\n" + KERNEL_ALPHA +
                        "endif()\n" + after + "endif()\n")
                with self.assertRaisesRegex(agc_test_split.SplitError, "order"):
                    agc_test_split.migrated(text, spec=agc_test_split.KERNEL_SPEC)

    def test_source_binding_overwrite_cannot_be_reordered(self):
        text = ("if(BUILD_TESTING)\n"
                "set(shared_source Zeta.cpp)\n"
                "add_test_executable(kernel_zeta_tests ${shared_source})\n"
                "set(shared_source Alpha.cpp)\n"
                "add_test_executable(kernel_alpha_tests ${shared_source})\n"
                "endif()\n")
        with self.assertRaisesRegex(agc_test_split.SplitError, "order"):
            agc_test_split.migrated(text, spec=agc_test_split.KERNEL_SPEC)

    def test_target_property_source_binding_cannot_be_reordered(self):
        for getter in ("get_target_property(zeta_sources kernel_zeta_tests SOURCES)",
                       "get_property(zeta_sources TARGET kernel_zeta_tests PROPERTY SOURCES)"):
            with self.subTest(getter=getter):
                text = ("if(BUILD_TESTING)\n"
                        "add_test_executable(kernel_zeta_tests Zeta.cpp)\n" + getter + "\n"
                        "add_test_executable(kernel_alpha_tests ${zeta_sources})\n"
                        "endif()\n")
                with self.assertRaisesRegex(agc_test_split.SplitError, "order"):
                    agc_test_split.migrated(text, spec=agc_test_split.KERNEL_SPEC)

    def test_directory_variable_queries_cannot_be_hoisted_across_a_write(self):
        text = ("if(BUILD_TESTING)\n"
                "set(shared_source Zeta.cpp)\n"
                "add_test_executable(kernel_zeta_tests Zeta.cpp)\n"
                "get_directory_property(alpha_sources DEFINITION shared_source)\n"
                "add_test_executable(kernel_alpha_tests ${alpha_sources})\n"
                "set(shared_source Alpha.cpp)\n"
                "endif()\n")
        with self.assertRaisesRegex(agc_test_split.SplitError, "order"):
            agc_test_split.migrated(text, spec=agc_test_split.KERNEL_SPEC)

    def test_string_output_bindings_cannot_be_reordered(self):
        for operation in ("CONCAT shared_source {source}",
                          "REPLACE unused ignored shared_source {source}",
                          "TOLOWER {source} shared_source",
                          "REGEX REPLACE unused ignored shared_source {source}"):
            with self.subTest(operation=operation):
                text = ("if(BUILD_TESTING)\n"
                        "string(" + operation.format(source="Zeta.cpp") + ")\n"
                        "add_test_executable(kernel_zeta_tests ${shared_source})\n"
                        "string(" + operation.format(source="Alpha.cpp") + ")\n"
                        "add_test_executable(kernel_alpha_tests ${shared_source})\n"
                        "endif()\n")
                with self.assertRaisesRegex(agc_test_split.SplitError, "order"):
                    agc_test_split.migrated(text, spec=agc_test_split.KERNEL_SPEC)

    def test_list_mutations_cannot_be_hoisted_before_a_reader(self):
        text = ("if(BUILD_TESTING)\n"
                "list(APPEND shared_source Zeta.cpp)\n"
                "add_test_executable(kernel_zeta_tests ${shared_source})\n"
                "list(POP_BACK shared_source)\n"
                "list(APPEND shared_source Alpha.cpp)\n"
                "add_test_executable(kernel_alpha_tests ${shared_source})\n"
                "endif()\n")
        with self.assertRaisesRegex(agc_test_split.SplitError, "order"):
            agc_test_split.migrated(text, spec=agc_test_split.KERNEL_SPEC)

    def test_list_and_file_output_bindings_cannot_be_reordered(self):
        for before, after, prefix in (("list(GET sources 0 shared_source)", "list(GET sources 1 shared_source)",
                                       "set(sources Zeta.cpp Alpha.cpp)\n"),
                                      ("file(READ Zeta.txt shared_source)", "file(READ Alpha.txt shared_source)", "")):
            with self.subTest(before=before):
                text = ("if(BUILD_TESTING)\n" + prefix + before + "\n"
                        "add_test_executable(kernel_zeta_tests ${shared_source})\n" + after + "\n"
                        "add_test_executable(kernel_alpha_tests ${shared_source})\n"
                        "endif()\n")
                diagnostic = "order" if before.startswith("list") else "unsupported file"
                with self.assertRaisesRegex(agc_test_split.SplitError, diagnostic):
                    agc_test_split.migrated(text, spec=agc_test_split.KERNEL_SPEC)

    def test_property_keywords_are_not_variable_writes(self):
        text = ("if(BUILD_TESTING)\n"
                "set(SOURCES original_value)\n"
                "add_test_executable(kernel_zeta_tests Zeta.cpp)\n"
                "get_target_property(zeta_sources kernel_zeta_tests SOURCES)\n"
                "add_test_executable(kernel_alpha_tests Alpha.cpp)\n"
                "target_compile_definitions(kernel_alpha_tests PRIVATE ${SOURCES})\n"
                "endif()\n")
        lists, fragments = agc_test_split.migrated(text, spec=agc_test_split.KERNEL_SPEC)
        self.assertEqual(sorted(fragments), ["kernel_alpha_tests", "kernel_zeta_tests"])
        self.assertIn("set(SOURCES original_value)", lists)
        self.assertIn("get_target_property(zeta_sources kernel_zeta_tests SOURCES)", fragments["kernel_zeta_tests"])
        self.assertIn("PRIVATE ${SOURCES}", fragments["kernel_alpha_tests"])

    def test_compound_target_and_test_conditions_cannot_be_reordered(self):
        zeta = KERNEL_BETA.replace("beta", "zeta")
        for condition in ("TARGET kernel_zeta_tests", "TEST kernel_zeta"):
            for branch in ("if(" + condition + ")\n", "if(FALSE)\nmessage(STATUS unused)\nelseif(" + condition + ")\n"):
                with self.subTest(condition=condition, branch=branch):
                    text = ("if(BUILD_TESTING)\n" + zeta + branch + KERNEL_ALPHA +
                            "else()\nmessage(STATUS absent)\nendif()\nendif()\n")
                    with self.assertRaisesRegex(agc_test_split.SplitError, "order"):
                        agc_test_split.migrated(text, spec=agc_test_split.KERNEL_SPEC)

    def test_macro_parent_scope_and_cache_effects_require_manual_migration(self):
        setters = ("macro(remember_source value)\nset(shared_source ${value})\nendmacro()\n",
                   "function(remember_source value)\nset(shared_source ${value} PARENT_SCOPE)\nendfunction()\n",
                   "set(shared_source Zeta.cpp CACHE STRING source)\n",
                   "unset(shared_source CACHE)\n",
                   "get_filename_component(shared_source Zeta.cpp ABSOLUTE CACHE)\n")
        for setter in setters:
            with self.subTest(setter=setter):
                with self.assertRaisesRegex(agc_test_split.SplitError, "effects require a manual migration"):
                    agc_test_split.migrated(kernel_original(prefix=setter), spec=agc_test_split.KERNEL_SPEC)

    def test_unsupported_variable_writer_forms_require_manual_migration(self):
        for command in ("string(CONFIGURE @source@ configured_source)",
                        "list(TRANSFORM sources TOUPPER OUTPUT_VARIABLE upper_sources)",
                        "file(GET_RUNTIME_DEPENDENCIES RESOLVED_DEPENDENCIES_VAR dependencies)",
                        "cmake_path(GET source FILENAME filename)"):
            with self.subTest(command=command):
                with self.assertRaisesRegex(agc_test_split.SplitError, "unsupported .* effects require a manual migration"):
                    agc_test_split.migrated(kernel_original(prefix=command + "\n"), spec=agc_test_split.KERNEL_SPEC)

    def test_opaque_variable_effects_require_manual_migration_in_helpers_too(self):
        for command in ("include(extra.cmake)", "add_subdirectory(extra)", "cmake_language(EVAL CODE extra)",
                        "foreach(source IN ZIP_LISTS alpha beta)\nendforeach()", "block(PROPAGATE source)\nendblock()",
                        "return(PROPAGATE source)"):
            for helper in (False, True):
                with self.subTest(command=command, helper=helper):
                    prefix = "function(register_cases)\n" + command + "\nendfunction()\n" if helper else command + "\n"
                    with self.assertRaisesRegex(agc_test_split.SplitError, "unsupported .* effects require a manual migration"):
                        agc_test_split.migrated(kernel_original(prefix=prefix), spec=agc_test_split.KERNEL_SPEC)

    def test_match_condition_captures_cannot_be_reordered(self):
        text = ("if(BUILD_TESTING)\n"
                "if(Zeta.cpp MATCHES \"(.*)\")\n"
                "add_test_executable(kernel_zeta_tests Zeta.cpp)\n"
                "endif()\n"
                "add_test_executable(kernel_alpha_tests ${CMAKE_MATCH_1})\n"
                "endif()\n")
        with self.assertRaisesRegex(agc_test_split.SplitError, "order"):
            agc_test_split.migrated(text, spec=agc_test_split.KERNEL_SPEC)

    def test_local_helpers_cannot_read_reordered_caller_bindings(self):
        for transitive in (False, True):
            with self.subTest(transitive=transitive):
                helper = ("function(add_kernel_case target)\n" +
                          ("add_kernel_target(${target})\nendfunction()\nfunction(add_kernel_target target)\n" if transitive else "") +
                          "add_executable(${target} ${shared_source})\nendfunction()\n")
                text = (helper + "if(BUILD_TESTING)\n"
                        "set(shared_source Zeta.cpp)\n"
                        "add_kernel_case(kernel_zeta_tests)\n"
                        "set(shared_source Alpha.cpp)\n"
                        "add_kernel_case(kernel_alpha_tests)\n"
                        "endif()\n")
                with self.assertRaisesRegex(agc_test_split.SplitError, "order"):
                    agc_test_split.migrated(text, spec=agc_test_split.KERNEL_SPEC)

    def test_cmake_target_initializers_cannot_be_reordered(self):
        text = ("if(BUILD_TESTING)\n"
                "set(CMAKE_CXX_STANDARD 20)\n"
                "add_test_executable(kernel_zeta_tests Zeta.cpp)\n"
                "set(CMAKE_CXX_STANDARD 23)\n"
                "add_test_executable(kernel_alpha_tests Alpha.cpp)\n"
                "endif()\n")
        with self.assertRaisesRegex(agc_test_split.SplitError, "order"):
            agc_test_split.migrated(text, spec=agc_test_split.KERNEL_SPEC)

    def test_repository_helper_parameters_cannot_be_reordered_through_local_wrappers(self):
        cases = (("add_test_executable", "ANYPS5_TEST_OUTPUT_DIRECTORY", "zeta", "alpha"),
                 ("add_test_executable", "MINGW", "OFF", "ON"),
                 ("configure_host_test_executable", "MINGW", "OFF", "ON"),
                 ("add_asan_test_options", "ANYPS5_ENABLE_ASAN", "OFF", "ON"),
                 ("configure_windows_unwind", "MINGW", "OFF", "ON"),
                 ("configure_windows_unwind", "CMAKE_OBJCOPY", "zeta-objcopy", "alpha-objcopy"),
                 ("configure_macos_unwind", "APPLE", "OFF", "ON"))
        for helper, variable, before, after in cases:
            for wrapped in (False, True):
                with self.subTest(helper=helper, variable=variable, wrapped=wrapped):
                    def registration(target, source):
                        if helper == "add_test_executable":
                            return f"add_test_executable({target} {source})\n"
                        defined = f"add_executable({target} {source})\n"
                        if helper == "add_asan_test_options":
                            return defined + f"add_test(NAME {target} COMMAND {target})\nadd_asan_test_options({target} verify_asan_link_order=0)\n"
                        return defined + f"{helper}({target})\n"

                    prefix = ""
                    zeta = registration("kernel_zeta_tests", "Zeta.cpp")
                    alpha = registration("kernel_alpha_tests", "Alpha.cpp")
                    if wrapped:
                        prefix = ("function(register_case target source)\n" + registration("${target}", "${source}") +
                                  "endfunction()\nfunction(delegate_case target source)\n"
                                  "register_case(${target} ${source})\nendfunction()\n")
                        zeta = "delegate_case(kernel_zeta_tests Zeta.cpp)\n"
                        alpha = "delegate_case(kernel_alpha_tests Alpha.cpp)\n"
                    text = (prefix + "if(BUILD_TESTING)\n" + f"set({variable} {before})\n" + zeta +
                            f"set({variable} {after})\n" + alpha + "endif()\n")
                    with self.assertRaisesRegex(agc_test_split.SplitError, "order"):
                        agc_test_split.migrated(text, spec=agc_test_split.KERNEL_SPEC)

    def test_directory_and_global_state_changes_require_manual_migration(self):
        for command in ("include_directories(include)", "link_directories(libs)", "link_libraries(extra)",
                        "add_definitions(-DADDED)", "remove_definitions(-DREMOVED)", "add_compile_options(-O2)",
                        "add_link_options(-static)", "set_directory_properties(PROPERTIES COMPILE_OPTIONS -O2)",
                        "set_property(DIRECTORY PROPERTY COMPILE_OPTIONS -O2)", "set_property(GLOBAL PROPERTY EXAMPLE value)"):
            with self.subTest(command=command):
                with self.assertRaisesRegex(agc_test_split.SplitError, "unsupported .* effects require a manual migration"):
                    agc_test_split.migrated(kernel_original(prefix=command + "\n"), spec=agc_test_split.KERNEL_SPEC)

    def test_library_specs_are_immutable_and_do_not_change_each_other(self):
        agc_before = agc_test_split.migrated(original(), EXECUTION)
        spec = agc_test_split.KERNEL_SPEC
        with self.assertRaises(AttributeError):
            spec.library = "libc"
        lists, fragments = agc_test_split.migrated(kernel_original(), spec=spec)
        self.assertEqual(sorted(fragments), ["kernel_alpha_tests", "kernel_beta_tests"])
        self.assertIn("file(GLOB kernelTestFragments CONFIGURE_DEPENDS", lists)
        self.assertNotIn("agcTestFragments", lists)
        self.assertIn("add_library(libkernel SHARED EXCLUDE_FROM_ALL Export.cpp)", lists)
        self.assertNotIn("kernel_alpha", lists)
        self.assertEqual(agc_test_split.migrated(original(), EXECUTION), agc_before)
        self.assertEqual(agc_test_split.migrated(kernel_original(), spec=spec), (lists, fragments))

    def test_post_build_command_moves_with_its_target(self):
        command = ("    add_custom_command(TARGET kernel_alpha_tests POST_BUILD\n"
                   "        COMMAND ${CMAKE_COMMAND} -E echo $<TARGET_FILE:kernel_alpha_tests>\n"
                   "        VERBATIM)\n")
        lists, fragments = agc_test_split.migrated(kernel_original((KERNEL_ALPHA + command, KERNEL_BETA)),
                                                  spec=agc_test_split.KERNEL_SPEC)
        self.assertNotIn("add_custom_command", lists)
        self.assertIn(command, fragments["kernel_alpha_tests"])

    def test_agc_preserves_existing_post_build_command_placement(self):
        command = ("    add_custom_command(TARGET agc_alpha_tests POST_BUILD\n"
                   "        COMMAND ${CMAKE_COMMAND} -E echo $<TARGET_FILE:agc_alpha_tests>\n"
                   "        VERBATIM)\n")
        text = ("add_library(libSceAgcDriver SHARED Export.cpp)\n"
                "if(BUILD_TESTING)\n" + ALPHA + command + "endif()\n")
        lists, fragments = agc_test_split.split_text(text)
        self.assertIn(command, lists)
        self.assertNotIn("add_custom_command", fragments["agc_alpha_tests"])
        self.assertLess(lists.index(agc_test_split.INCLUDE[0]), lists.index("add_custom_command"))

    def test_shared_fixtures_and_registration_helpers_remain_in_parent(self):
        prefix = ("    add_library(kernel_fixture SHARED tests/Fixture.cpp)\n"
                  "    target_compile_definitions(kernel_fixture PRIVATE FIXTURE_COMPLETE)\n"
                  "    function(add_kernel_case name)\n"
                  "        add_test(NAME helper_${name} COMMAND kernel_alpha_tests ${name})\n"
                  "    endfunction()\n"
                  "    add_kernel_case(one)\n")
        lists, fragments = agc_test_split.migrated(kernel_original(prefix=prefix), spec=agc_test_split.KERNEL_SPEC)
        self.assertIn(prefix, lists)
        self.assertLess(lists.index("add_kernel_case(one)"), lists.index("file(GLOB kernelTestFragments"))
        self.assertNotIn("kernel_fixture", "".join(fragments.values()))


class KernelResolveTests(unittest.TestCase):
    def setUp(self):
        self.root = Path(tempfile.mkdtemp())
        self.spec = agc_test_split.KERNEL_SPEC
        self.git("init", "-q", "-b", "main")
        self.write(self.spec.lists, kernel_original())
        self.write(LISTS, original())
        self.commit("build: register tests")

    def tearDown(self):
        shutil.rmtree(self.root, ignore_errors=True)

    def git(self, *args, check=True):
        return subprocess.run(["git", "-c", "user.name=Split Test", "-c", "user.email=test@example.com", "-c", "commit.gpgsign=false",
                               "-c", "core.editor=true", *args], cwd=self.root, capture_output=True, text=True, check=check)

    def write(self, path, text):
        agc_test_split.write_lf(self.root / path, text)

    def read(self, path):
        return (self.root / path).read_text(encoding="utf-8")

    def fragment(self, name):
        return agc_test_split.fragment_path(name, self.spec)

    def tool(self, command):
        return subprocess.run([sys.executable, str(TOOL), "--library", "libkernel", command], cwd=self.root,
                              capture_output=True, text=True, timeout=60)

    def commit(self, message):
        self.git("add", "-A")
        self.git("commit", "-qm", message)

    def prepare_branches(self, change, after_split=None):
        self.git("checkout", "-qb", "change")
        self.write(self.spec.lists, change)
        self.commit("test(libkernel): change registrations")
        self.git("checkout", "-q", "main")
        result = self.tool("split")
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.commit("build(libkernel): split test registrations")
        if after_split:
            after_split()
            self.commit("test(libkernel): update split registrations")

    def resolve_rebase(self, change, after_split=None):
        self.prepare_branches(change, after_split)
        self.git("checkout", "-q", "change")
        self.assertNotEqual(self.git("rebase", "main", check=False).returncode, 0)
        return self.tool("resolve")

    def test_mtypeprotect_registration_migrates_during_a_rebase(self):
        result = self.resolve_rebase(kernel_original((KERNEL_ALPHA, KERNEL_BETA, MTYPEPROTECT)))
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.git("rebase", "--continue")
        self.assertEqual(self.read(self.fragment("guest_mtypeprotect_tests")), "if(BUILD_TESTING)\n" + MTYPEPROTECT + "endif()\n")
        self.assertEqual(self.read(self.spec.lists), self.git("show", "main:" + self.spec.lists).stdout)
        self.assertEqual(self.read(LISTS), original())

    def test_mtypeprotect_registration_migrates_with_either_split_merge_side(self):
        for split_is_ours in (True, False):
            with self.subTest(split_is_ours=split_is_ours):
                if self.git("branch", "--list", "change").stdout:
                    self.git("checkout", "-q", "main")
                    self.git("reset", "--hard", "HEAD~1")
                    self.git("branch", "-D", "change")
                self.prepare_branches(kernel_original((KERNEL_ALPHA, KERNEL_BETA, MTYPEPROTECT)))
                self.git("checkout", "-q", "main" if split_is_ours else "change")
                other = "change" if split_is_ours else "main"
                self.assertNotEqual(self.git("merge", "--no-commit", other, check=False).returncode, 0)
                result = self.tool("resolve")
                self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
                self.assertEqual(self.git("diff", "--name-only", "--diff-filter=U").stdout, "")
                self.assertIn("add_test(NAME guest_mtypeprotect", self.read(self.fragment("guest_mtypeprotect_tests")))
                self.git("merge", "--abort")

    def test_resolve_preserves_independent_fragment_edits(self):
        def later():
            path = self.fragment("kernel_alpha_tests")
            self.write(path, self.read(path).replace("PRIVATE libkernel libc", "PRIVATE libkernel libc Threads::Threads"))

        change = kernel_original((KERNEL_ALPHA.replace("TIMEOUT 20", "TIMEOUT 25"), KERNEL_BETA, MTYPEPROTECT))
        result = self.resolve_rebase(change, later)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.git("rebase", "--continue")
        alpha = self.read(self.fragment("kernel_alpha_tests"))
        self.assertIn("TIMEOUT 25", alpha)
        self.assertIn("PRIVATE libkernel libc Threads::Threads", alpha)
        self.assertTrue((self.root / self.fragment("guest_mtypeprotect_tests")).exists())

    def test_resolve_preserves_an_independent_new_fragment(self):
        gamma = ("if(BUILD_TESTING)\n"
                 "    add_test_executable(kernel_gamma_tests tests/Gamma.cpp)\n"
                 "    add_test(NAME kernel_gamma COMMAND kernel_gamma_tests)\n"
                 "endif()\n")

        def later():
            self.write(self.fragment("kernel_gamma_tests"), gamma)

        result = self.resolve_rebase(kernel_original((KERNEL_ALPHA, KERNEL_BETA, MTYPEPROTECT)), later)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.git("rebase", "--continue")
        self.assertEqual(self.read(self.fragment("kernel_gamma_tests")), gamma)
        self.assertIn("add_test(NAME guest_mtypeprotect", self.read(self.fragment("guest_mtypeprotect_tests")))

    def test_resolve_keeps_same_line_conflicts_visible_and_unstaged(self):
        def later():
            path = self.fragment("kernel_alpha_tests")
            self.write(path, self.read(path).replace("TIMEOUT 20", "TIMEOUT 60"))

        result = self.resolve_rebase(kernel_original((KERNEL_ALPHA.replace("TIMEOUT 20", "TIMEOUT 25"), KERNEL_BETA)), later)
        self.assertNotEqual(result.returncode, 0)
        path = self.fragment("kernel_alpha_tests")
        self.assertIn(path, result.stderr)
        self.assertIn("<<<<<<<", self.read(path))
        self.assertEqual(self.git("diff", "--cached", "--", path).stdout, "")

    def test_resolve_removes_a_deleted_registration(self):
        result = self.resolve_rebase(kernel_original((KERNEL_BETA,)))
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.git("rebase", "--continue")
        self.assertFalse((self.root / self.fragment("kernel_alpha_tests")).exists())
        self.assertTrue((self.root / self.fragment("kernel_beta_tests")).exists())

    def test_resolve_preserves_independent_production_changes(self):
        def later():
            self.write(self.spec.lists, self.read(self.spec.lists).replace("PRIVATE include", "PRIVATE include extra"))

        result = self.resolve_rebase(kernel_original((KERNEL_ALPHA, KERNEL_BETA, MTYPEPROTECT), library="Main.cpp"), later)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.git("rebase", "--continue")
        self.assertIn("SHARED EXCLUDE_FROM_ALL Main.cpp", self.read(self.spec.lists))
        self.assertIn("PRIVATE include extra", self.read(self.spec.lists))

    def test_split_and_refactor_refuse_without_changing_existing_files(self):
        before = self.read(self.spec.lists)
        result = self.tool("refactor")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("no registration loops", result.stderr)
        self.assertEqual(self.read(self.spec.lists), before)
        self.assertEqual(self.tool("split").returncode, 0)
        split = self.read(self.spec.lists)
        result = self.tool("split")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("already includes", result.stderr)
        self.assertEqual(self.read(self.spec.lists), split)
        self.assertEqual(self.read(LISTS), original())

    def check_unsafe_change_is_refused(self, change, diagnostic):
        self.prepare_branches(change)
        self.git("checkout", "-q", "change")
        self.assertNotEqual(self.git("rebase", "main", check=False).returncode, 0)
        before = {str(path.relative_to(self.root)): path.read_bytes() for path in self.root.rglob("*")
                  if path.is_file() and path.relative_to(self.root).parts[0] != ".git"}
        index = self.git("ls-files", "--stage", "-z").stdout
        result = self.tool("resolve")
        self.assertNotEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn(diagnostic, result.stderr)
        self.assertEqual(self.git("ls-files", "--stage", "-z").stdout, index)
        after = {str(path.relative_to(self.root)): path.read_bytes() for path in self.root.rglob("*")
                 if path.is_file() and path.relative_to(self.root).parts[0] != ".git"}
        self.assertEqual(after, before)

    def test_resolve_refuses_changed_list_context_without_writes(self):
        change = kernel_original((KERNEL_ALPHA, KERNEL_BETA, MTYPEPROTECT.replace("${LIBS_INCLUDE_DIR}", "${CMAKE_CURRENT_LIST_DIR}")))
        self.check_unsafe_change_is_refused(change, "list context")

    def test_resolve_refuses_changed_condition_order_without_writes(self):
        dependent = "if(TARGET kernel_zeta_tests)\n" + MTYPEPROTECT + "endif()\n"
        change = kernel_original((KERNEL_ALPHA, KERNEL_BETA, KERNEL_BETA.replace("beta", "zeta"), dependent))
        self.check_unsafe_change_is_refused(change, "order")

    def test_resolve_refuses_computed_variable_reads_without_writes(self):
        computed = ("add_test_executable(kernel_zeta_tests ${${selector}})\n"
                    "set(shared_source Alpha.cpp)\n"
                    "add_test_executable(kernel_gamma_tests ${${selector}})\n")
        change = kernel_original((KERNEL_ALPHA, KERNEL_BETA, computed),
                                 prefix="set(selector shared_source)\nset(shared_source Zeta.cpp)\n")
        self.check_unsafe_change_is_refused(change, "computed variable reference")


if __name__ == "__main__":
    unittest.main()
