import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from test_agc_test_split import KERNEL_ALPHA, KERNEL_BETA, TOOL, agc_test_split, kernel_original


class ResolveSafetyTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.spec = agc_test_split.KERNEL_SPEC

    def git(self, *args, check=True):
        result = subprocess.run(["git", "-c", "user.name=Split Test", "-c", "user.email=test@example.com",
                                 "-c", "commit.gpgsign=false", "-c", "core.editor=true", *args],
                                cwd=self.root, capture_output=True, text=True)
        if check:
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        return result

    def write(self, path, text):
        agc_test_split.write_lf(self.root / path, text)

    def read(self, path):
        return (self.root / path).read_text(encoding="utf-8")

    def fragment(self, name):
        return agc_test_split.fragment_path(name, self.spec)

    def commit(self, message):
        self.git("add", "-A")
        self.git("commit", "-qm", message)

    def tool(self, command="resolve"):
        return subprocess.run([sys.executable, str(TOOL), "--library", "libkernel", command],
                              cwd=self.root, capture_output=True, text=True, timeout=60)

    def repository(self, name, style="merge", marker_size=7, existing_fragment=False, parent_suffix=""):
        self.root = Path(self.temporary.name) / name
        self.root.mkdir()
        self.parent_suffix = parent_suffix
        self.git("init", "-q", "-b", "main")
        self.git("config", "merge.conflictStyle", style)
        if marker_size != 7:
            self.write(".gitattributes", f"{self.spec.lists} conflict-marker-size={marker_size}\n")
        self.write(self.spec.lists, kernel_original() + parent_suffix)
        self.write("unrelated.txt", "untouched\n")
        if existing_fragment:
            self.write(self.fragment("independent_tests"), 'message(STATUS "base")\n')
        self.commit("build: register tests")

    def branches(self, fragment_conflict=None, changed_alpha=None):
        self.git("checkout", "-qb", "change")
        changed = changed_alpha if changed_alpha is not None else KERNEL_ALPHA.replace("TIMEOUT 20", "TIMEOUT 25")
        self.write(self.spec.lists, kernel_original((changed, KERNEL_BETA)) + self.parent_suffix)
        if fragment_conflict == "add":
            alpha = KERNEL_ALPHA.replace("PRIVATE libkernel libc", "PRIVATE libkernel libc PRIVATE_FIX")
            self.write(self.fragment("kernel_alpha_tests"), "if(BUILD_TESTING)\n" + alpha + "endif()\n")
        elif fragment_conflict == "modify":
            self.write(self.fragment("independent_tests"), 'message(STATUS "change")\n')
        self.commit("test: change registrations")
        self.git("checkout", "-q", "main")
        result = self.tool("split")
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        if fragment_conflict == "modify":
            self.write(self.fragment("independent_tests"), 'message(STATUS "split")\n')
        self.commit("build: split registrations")

    def stop(self, mode, split_is_current):
        self.git("checkout", "-q", "main" if split_is_current else "change")
        other = "change" if split_is_current else "main"
        args = ("merge", "--no-commit", other) if mode == "merge" else ("rebase", other)
        result = self.git(*args, check=False)
        self.assertNotEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertTrue(self.git("ls-files", "-u", "--", self.spec.lists).stdout)

    def snapshot(self):
        files = {}
        for path in self.root.rglob("*"):
            relative = path.relative_to(self.root)
            if relative.parts[0] == ".git":
                continue
            if path.is_symlink():
                files[str(relative)] = ("symlink", str(path.readlink()))
            elif path.is_file():
                files[str(relative)] = ("file", path.stat().st_mode & 0o777, path.read_bytes())
        return files, self.git("ls-files", "--stage", "-z").stdout, self.git("ls-files", "-v", "-z").stdout

    def assert_refused_unchanged(self, message):
        before = self.snapshot()
        result = self.tool()
        self.assertNotEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn(message, result.stderr)
        self.assertNotIn("Traceback", result.stderr)
        self.assertEqual(self.snapshot(), before)

    def test_untouched_parent_conflicts_resolve_for_all_styles_and_sides(self):
        for style in ("merge", "diff3", "zdiff3"):
            for mode in ("merge", "rebase"):
                for split_is_current in (True, False):
                    with self.subTest(style=style, mode=mode, split_is_current=split_is_current):
                        self.repository(f"{style}-{mode}-{split_is_current}", style)
                        self.branches()
                        self.stop(mode, split_is_current)
                        result = self.tool()
                        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
                        self.assertEqual(self.git("ls-files", "-u").stdout, "")
                        self.assertIn("TIMEOUT 25", self.read(self.fragment("kernel_alpha_tests")))
                        self.assertEqual(self.read("unrelated.txt"), "untouched\n")

    def test_custom_conflict_marker_size_is_respected(self):
        for style in ("merge", "diff3", "zdiff3"):
            for marker_size in (3, 11):
                with self.subTest(style=style, marker_size=marker_size):
                    self.repository(f"{style}-{marker_size}", style, marker_size=marker_size)
                    self.branches()
                    self.stop("merge", True)
                    self.assertIn("<" * marker_size, self.read(self.spec.lists))
                    result = self.tool()
                    self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_production_edits_in_conflicted_parent_are_preserved(self):
        for mode in ("merge", "rebase"):
            for split_is_current in (True, False):
                with self.subTest(mode=mode, split_is_current=split_is_current):
                    self.repository(f"{mode}-{split_is_current}")
                    self.branches()
                    self.stop(mode, split_is_current)
                    self.write(self.spec.lists, self.read(self.spec.lists).replace("PRIVATE include", "PRIVATE include LOCAL_FIX"))
                    self.assert_refused_unchanged("working-tree edits")

    def test_partial_and_complete_parent_resolutions_are_preserved(self):
        for fully_resolved in (True, False):
            with self.subTest(fully_resolved=fully_resolved):
                self.repository(str(fully_resolved))
                self.branches()
                self.stop("rebase", False)
                text = self.git("show", "main:" + self.spec.lists).stdout if fully_resolved else self.read(self.spec.lists)
                self.write(self.spec.lists, text.replace("PRIVATE include", "PRIVATE include MANUAL_RESOLUTION"))
                self.assert_refused_unchanged("working-tree edits")

    def test_existing_add_add_fragment_conflicts_are_preserved_for_all_sides(self):
        for mode in ("merge", "rebase"):
            for split_is_current in (True, False):
                with self.subTest(mode=mode, split_is_current=split_is_current):
                    self.repository(f"{mode}-{split_is_current}")
                    self.branches("add")
                    self.stop(mode, split_is_current)
                    fragment = self.fragment("kernel_alpha_tests")
                    self.assertTrue(self.git("ls-files", "-u", "--", fragment).stdout)
                    self.assertIn("<<<<<<<", self.read(fragment))
                    self.assert_refused_unchanged("unresolved fragment conflicts")

    def test_existing_modified_fragment_conflicts_are_preserved(self):
        for mode in ("merge", "rebase"):
            with self.subTest(mode=mode):
                self.repository(mode, existing_fragment=True)
                self.branches("modify")
                self.stop(mode, True)
                fragment = self.fragment("independent_tests")
                self.assertIn(" 1\t", self.git("ls-files", "-u", "--", fragment).stdout)
                self.assert_refused_unchanged("unresolved fragment conflicts")

    def test_local_fragment_markers_are_not_staged_as_resolved(self):
        for marker_size in (3, 7):
            with self.subTest(marker_size=marker_size):
                self.repository(str(marker_size))
                self.branches()
                self.stop("rebase", False)
                fragment = self.fragment("kernel_alpha_tests")
                self.write(".gitattributes", f"{fragment} conflict-marker-size={marker_size}\n")
                markers = "<" * marker_size + " local\n" + "=" * marker_size + "\n" + ">" * marker_size + " other\n"
                self.write(fragment, self.read(fragment).replace("    target_link_libraries", markers + "    target_link_libraries"))
                self.assertEqual(self.git("ls-files", "-u", "--", fragment).stdout, "")
                self.assert_refused_unchanged("contains conflict markers")

    def test_partially_staged_fragment_edits_are_preserved(self):
        for mode in ("merge", "rebase"):
            for split_is_current in (True, False):
                for unstaged_fix in ("", " LOCAL_FIX"):
                    with self.subTest(mode=mode, split_is_current=split_is_current, unstaged_fix=unstaged_fix):
                        self.repository(f"{mode}-{split_is_current}-{bool(unstaged_fix)}")
                        self.branches()
                        self.stop(mode, split_is_current)
                        fragment = self.fragment("kernel_alpha_tests")
                        original = self.read(fragment)
                        self.write(fragment, original.replace("PRIVATE libkernel libc", "PRIVATE libkernel libc STAGED_FIX"))
                        self.git("add", "--", fragment)
                        self.write(fragment, original.replace("PRIVATE libkernel libc", "PRIVATE libkernel libc" + unstaged_fix))
                        self.assert_refused_unchanged("different index and working-tree contents")

    def test_staged_fragment_deletion_with_local_recreation_is_preserved(self):
        for mode in ("merge", "rebase"):
            with self.subTest(mode=mode):
                self.repository(mode)
                self.branches()
                self.stop(mode, True)
                fragment = self.fragment("kernel_alpha_tests")
                original = self.read(fragment)
                self.git("rm", "-qf", "--", fragment)
                self.write(fragment, original.replace("PRIVATE libkernel libc", "PRIVATE libkernel libc LOCAL_RECREATION"))
                self.assert_refused_unchanged("different index and working-tree contents")

    def test_staged_fragment_edits_with_matching_worktree_still_merge(self):
        for mode in ("merge", "rebase"):
            for split_is_current in (True, False):
                with self.subTest(mode=mode, split_is_current=split_is_current):
                    self.repository(f"{mode}-{split_is_current}")
                    self.branches()
                    self.stop(mode, split_is_current)
                    fragment = self.fragment("kernel_alpha_tests")
                    self.write(fragment, self.read(fragment).replace("PRIVATE libkernel libc", "PRIVATE libkernel libc STAGED_FIX"))
                    self.git("add", "--", fragment)
                    result = self.tool()
                    self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
                    self.assertIn("STAGED_FIX", self.read(fragment))
                    self.assertIn("TIMEOUT 25", self.read(fragment))
                    self.assertEqual(self.git("show", ":" + fragment).stdout, self.read(fragment))

    def test_untouched_fragment_worktree_edits_remain_local(self):
        self.repository("untouched-local-edits")
        self.branches()
        self.stop("rebase", False)
        fragment = self.fragment("kernel_beta_tests")
        staged = self.git("show", ":" + fragment).stdout
        local = self.read(fragment).replace("COMMAND kernel_beta_tests", "COMMAND kernel_beta_tests LOCAL_FIX")
        self.write(fragment, local)
        result = self.tool()
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual(self.read(fragment), local)
        self.assertEqual(self.git("show", ":" + fragment).stdout, staged)

    def test_index_flags_do_not_hide_partially_staged_fragment_edits(self):
        for flag in ("--assume-unchanged", "--skip-worktree"):
            with self.subTest(flag=flag):
                self.repository(flag)
                self.branches()
                self.stop("rebase", False)
                fragment = self.fragment("kernel_alpha_tests")
                original = self.read(fragment)
                self.write(fragment, original.replace("PRIVATE libkernel libc", "PRIVATE libkernel libc STAGED_FIX"))
                self.git("add", "--", fragment)
                self.git("update-index", flag, "--", fragment)
                self.write(fragment, original)
                self.assert_refused_unchanged("different index and working-tree contents")

    def test_clean_flagged_fragments_are_refused_before_they_can_be_changed(self):
        for flag in ("--assume-unchanged", "--skip-worktree"):
            with self.subTest(flag=flag):
                self.repository(flag)
                self.branches()
                self.stop("rebase", False)
                fragment = self.fragment("kernel_alpha_tests")
                self.git("update-index", flag, "--", fragment)
                self.assert_refused_unchanged("index flags that prevent safe staging")

    def test_normal_checkout_line_endings_do_not_look_like_local_edits(self):
        self.repository("crlf-checkout")
        self.branches()
        self.stop("rebase", False)
        fragment = self.fragment("kernel_alpha_tests")
        self.git("config", "core.autocrlf", "true")
        (self.root / fragment).write_bytes(self.read(fragment).replace("\n", "\r\n").encode("utf-8"))
        result = self.tool()
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("TIMEOUT 25", self.read(fragment))

    def test_edited_marker_shaped_production_literals_are_preserved(self):
        for character in ("<", "|", ">"):
            with self.subTest(character=character):
                literal = 'set(production_text [=[\n' + character * 7 + ' old\n]=])\n'
                self.repository(str(ord(character)), parent_suffix=literal)
                self.branches()
                self.stop("rebase", False)
                changed = self.read(self.spec.lists).replace(character * 7 + " old", character * 7 + " local_user_edit")
                self.write(self.spec.lists, changed)
                self.assert_refused_unchanged("working-tree edits")

    def test_unchanged_marker_shaped_production_literals_still_resolve(self):
        literal = ('set(production_text [=[\n'
                   '<<<<<<< anyps5-resolver-conflict ours\n'
                   '||||||| old\n'
                   '>>>>>>> old\n'
                   ']=])\n')
        for style in ("merge", "diff3", "zdiff3"):
            with self.subTest(style=style):
                self.repository(style, style, parent_suffix=literal)
                self.branches()
                self.stop("merge", True)
                result = self.tool()
                self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
                self.assertIn(literal, self.read(self.spec.lists))
                self.assertIn("TIMEOUT 25", self.read(self.fragment("kernel_alpha_tests")))

    @unittest.skipIf(sys.platform == "win32", "needs executable mode bits")
    def test_staged_fragment_mode_reversals_are_preserved(self):
        for executable in (True, False):
            with self.subTest(executable=executable):
                self.repository(str(executable))
                self.git("config", "core.filemode", "true")
                self.branches()
                fragment = self.fragment("kernel_alpha_tests")
                file = self.root / fragment
                if not executable:
                    file.chmod(file.stat().st_mode | 0o111)
                    self.commit("test: register executable fragment")
                self.stop("rebase", False)
                file.chmod(file.stat().st_mode | 0o111 if executable else file.stat().st_mode & ~0o111)
                self.git("add", "--", fragment)
                file.chmod(file.stat().st_mode & ~0o111 if executable else file.stat().st_mode | 0o111)
                self.assertIn("100755" if executable else "100644", self.git("ls-files", "--stage", "--", fragment).stdout)
                self.assert_refused_unchanged("different index and working-tree modes")

    @unittest.skipIf(sys.platform == "win32", "needs executable mode bits")
    def test_ignored_worktree_modes_do_not_change_staged_modes(self):
        for executable in (True, False):
            with self.subTest(executable=executable):
                self.repository(str(executable))
                self.branches()
                self.stop("rebase", False)
                self.git("config", "core.filemode", "false")
                fragment = self.fragment("kernel_alpha_tests")
                file = self.root / fragment
                self.git("update-index", "--chmod=+x" if executable else "--chmod=-x", "--", fragment)
                file.chmod(file.stat().st_mode & ~0o111 if executable else file.stat().st_mode | 0o111)
                result = self.tool()
                self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
                self.assertIn("TIMEOUT 25", self.read(fragment))
                self.assertIn("100755" if executable else "100644", self.git("ls-files", "--stage", "--", fragment).stdout)

    def test_non_utf8_fragment_conversion_is_refused_before_writing(self):
        self.repository("latin1-fragments")
        self.write(".gitattributes", "*.cmake working-tree-encoding=ISO-8859-1\n")
        self.commit("build: configure fragment encoding")
        self.branches(changed_alpha=KERNEL_ALPHA.replace("TIMEOUT 20", 'TIMEOUT 25 LABELS "café"'))
        self.stop("rebase", False)
        self.assert_refused_unchanged("working-tree-encoding=ISO-8859-1")

    def test_parent_encoding_is_checked_before_utf8_reads(self):
        self.repository("latin1-parent", parent_suffix='set(production_label "café")\n')
        self.branches()
        self.stop("rebase", False)
        parent = self.root / self.spec.lists
        parent.write_bytes(self.read(self.spec.lists).encode("iso-8859-1"))
        self.write(".gitattributes", f"{self.spec.lists} working-tree-encoding=ISO-8859-1\n")
        self.assert_refused_unchanged("working-tree-encoding=ISO-8859-1")

    def test_custom_parent_and_fragment_content_filters_are_refused(self):
        for parent in (True, False):
            for driver in ("review", "unset", "unspecified"):
                with self.subTest(parent=parent, driver=driver):
                    self.repository(f"{parent}-{driver}")
                    self.branches()
                    self.stop("rebase", False)
                    command = f'"{sys.executable}" -c "import sys; sys.stdout.buffer.write(sys.stdin.buffer.read())"'
                    self.git("config", f"filter.{driver}.clean", command)
                    self.git("config", f"filter.{driver}.smudge", command)
                    path = self.spec.lists if parent else self.fragment("kernel_alpha_tests")
                    self.write(".gitattributes", f"{path} filter={driver}\n")
                    self.assert_refused_unchanged(f"uses a Git content filter ({driver})")

    def test_invalid_literal_encoding_status_names_are_refused_without_writes(self):
        for encoding in ("unset", "unspecified"):
            with self.subTest(encoding=encoding):
                self.repository(encoding)
                self.branches()
                self.stop("rebase", False)
                self.write(".gitattributes", f"{self.spec.lists} working-tree-encoding={encoding}\n")
                self.assert_refused_unchanged("unsupported Git content conversion attributes")

    def test_utf8_and_unconfigured_regular_files_keep_non_ascii_labels(self):
        for encoding in (None, "UTF-8", "UTF8"):
            with self.subTest(encoding=encoding):
                self.repository(str(encoding))
                if encoding:
                    self.write(".gitattributes", f"*.cmake working-tree-encoding={encoding}\n"
                               f"{self.spec.lists} working-tree-encoding={encoding}\n")
                    self.commit("build: configure UTF-8 checkout")
                self.branches(changed_alpha=KERNEL_ALPHA.replace("TIMEOUT 20", 'TIMEOUT 25 LABELS "café"'))
                self.stop("rebase", False)
                result = self.tool()
                self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
                fragment = self.fragment("kernel_alpha_tests")
                self.assertIn('LABELS "café"', self.read(fragment))
                self.assertEqual(self.git("show", ":" + fragment).stdout, self.read(fragment))

    def test_unrelated_fragment_attributes_do_not_block_resolution(self):
        self.repository("unrelated-conversion")
        self.branches()
        self.stop("rebase", False)
        fragment = self.fragment("kernel_beta_tests")
        original = (self.root / fragment).read_bytes()
        self.write(".gitattributes", f"{fragment} working-tree-encoding=ISO-8859-1 filter=unrelated\n")
        result = self.tool()
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual((self.root / fragment).read_bytes(), original)
        self.assertIn("TIMEOUT 25", self.read(self.fragment("kernel_alpha_tests")))

    def test_invalid_utf8_is_reported_without_writes_or_traceback(self):
        for parent in (True, False):
            with self.subTest(parent=parent):
                self.repository(str(parent))
                self.branches()
                self.stop("rebase", False)
                path = self.root / (self.spec.lists if parent else self.fragment("kernel_alpha_tests"))
                path.write_bytes(path.read_bytes() + b"\xff")
                self.assert_refused_unchanged("utf-8")

    @unittest.skipIf(sys.platform == "win32", "needs symbolic link creation")
    def test_symlinked_parent_preserves_the_link_and_target(self):
        for mode in ("merge", "rebase"):
            for split_is_current in (True, False):
                with self.subTest(mode=mode, split_is_current=split_is_current):
                    self.repository(f"{mode}-{split_is_current}")
                    self.branches()
                    self.stop(mode, split_is_current)
                    parent = self.root / self.spec.lists
                    target = self.root / "saved-conflict.txt"
                    original = parent.read_bytes()
                    target.write_bytes(original)
                    parent.unlink()
                    parent.symlink_to(target)
                    self.assert_refused_unchanged("parent must be a regular file")
                    self.assertTrue(parent.is_symlink())
                    self.assertEqual(parent.readlink(), target)
                    self.assertEqual(target.read_bytes(), original)

    def test_non_regular_parent_index_stages_are_refused(self):
        for stage in ("1", "2", "3"):
            with self.subTest(stage=stage):
                self.repository(stage)
                self.branches()
                self.stop("rebase", False)
                entries = self.git("ls-files", "-u", "--", self.spec.lists).stdout.splitlines()
                entry = next(line for line in entries if line.split("\t", 1)[0].split()[2] == stage)
                _, blob, _ = entry.split("\t", 1)[0].split()
                result = subprocess.run(["git", "update-index", "--index-info"], cwd=self.root, capture_output=True,
                                        text=True, input=f"120000 {blob} {stage}\t{self.spec.lists}\n")
                self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
                self.assert_refused_unchanged("parent must be a regular file")


if __name__ == "__main__":
    unittest.main()
