import argparse
import re
import subprocess
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

LISTS = "core/libs/prx/libSceAgcDriver/CMakeLists.txt"
FRAGMENTS = "core/libs/prx/libSceAgcDriver/tests/cmake"
EXECUTION = "core/libs/prx/libSceAgcDriver/tests/execution"
INCLUDE = [
    "file(GLOB agcTestFragments CONFIGURE_DEPENDS ${CMAKE_CURRENT_SOURCE_DIR}/tests/cmake/*.cmake)",
    "list(SORT agcTestFragments)",
    "foreach(agcTestFragment IN LISTS agcTestFragments)",
    "    include(${agcTestFragment})",
    "endforeach()",
]


@dataclass(frozen=True)
class SplitSpec:
    library: str = "libSceAgcDriver"
    variable: str = "agcTest"
    execution: Optional[str] = EXECUTION
    custom_target_commands: bool = False
    strict: bool = False

    @property
    def lists(self):
        return f"core/libs/prx/{self.library}/CMakeLists.txt"

    @property
    def fragments(self):
        return f"core/libs/prx/{self.library}/tests/cmake"

    @property
    def include(self):
        return [
            f"file(GLOB {self.variable}Fragments CONFIGURE_DEPENDS ${{CMAKE_CURRENT_SOURCE_DIR}}/tests/cmake/*.cmake)",
            f"list(SORT {self.variable}Fragments)",
            f"foreach({self.variable}Fragment IN LISTS {self.variable}Fragments)",
            f"    include(${{{self.variable}Fragment}})",
            "endforeach()",
        ]


AGC_SPEC = SplitSpec()
KERNEL_SPEC = SplitSpec("libkernel", "kernelTest", None, True, True)

OPEN = {"if": "endif", "foreach": "endforeach", "while": "endwhile", "function": "endfunction", "macro": "endmacro", "block": "endblock"}
BRANCH = {"elseif", "else"}
CALL = re.compile(r"[ \t]*([A-Za-z_][A-Za-z0-9_]*)[ \t]*\(")
UNIT = re.compile(r"[a-z][a-z0-9_]*_tests")
MENTION = re.compile(r"(?<![A-Za-z0-9_{])[a-z][a-z0-9_]*_tests(?![A-Za-z0-9_])")
VARIABLE = re.compile(r"\$\{([A-Za-z0-9_]+)\}")
IDENT = re.compile(r"[A-Za-z_][A-Za-z0-9_]*")
SPECIAL = re.compile(r'if\(agcTestName STREQUAL "([A-Za-z0-9_]+)"\)')
DEFINERS = {"add_executable", "add_test_executable", "add_library", "add_custom_target"}
SUBJECT_FIRST = {"target_link_libraries", "target_include_directories", "target_compile_definitions", "target_compile_options",
                 "target_sources", "target_link_options", "target_compile_features", "target_precompile_headers",
                 "configure_windows_unwind", "add_dependencies"}
CONTROL = {"if", "elseif", "else", "endif", "foreach", "endforeach", "while", "endwhile", "function", "endfunction", "macro",
           "endmacro", "block", "endblock", "return", "break", "continue", "set", "unset", "list", "string", "file", "message",
           "math", "option", "include", "get_filename_component", "add_custom_command", "add_subdirectory", "cmake_path",
           "set_source_files_properties", "separate_arguments"}
SETTERS = {"set", "unset", "option", "list", "string", "math", "file", "get_filename_component", "get_target_property",
           "get_test_property", "get_directory_property", "get_property", "cmake_path", "separate_arguments", "foreach"}
LIST_READERS = {"APPEND", "PREPEND", "INSERT", "REMOVE_ITEM", "REMOVE_AT", "REMOVE_DUPLICATES", "FILTER", "SORT", "REVERSE",
                "TRANSFORM", "POP_BACK", "POP_FRONT", "GET", "LENGTH", "FIND", "JOIN"}
HELPERS = {
    "agc_add_default_test": lambda target: (target, [target[:-6]]),
    "agc_add_draw_pipeline_test": lambda stem: (stem + "_tests", [stem + "_draw_pipeline"]),
    "agc_add_spirv_mode_tests": lambda target: (target, [target[:-6], target[:-6] + "_full", target[:-6] + "_none"]),
}
TEST_KEYWORDS = {"CONFIGURATIONS", "WORKING_DIRECTORY", "COMMAND_EXPAND_LISTS"}
STRICT_OPAQUE = {"cmake_path", "execute_process", "find_file", "find_library", "find_path", "find_program", "load_cache",
                 "include", "add_subdirectory", "cmake_language", "include_directories", "link_directories", "link_libraries",
                 "add_definitions", "remove_definitions", "add_compile_options", "add_link_options", "set_directory_properties",
                 "set_source_files_properties", "cmake_policy"}
KERNEL_HELPER_READS = {
    "add_test_executable": {"ANYPS5_TEST_OUTPUT_DIRECTORY", "MINGW"},
    "configure_host_test_executable": {"MINGW"},
    "add_asan_test_options": {"ANYPS5_ENABLE_ASAN"},
    "configure_windows_unwind": {"MINGW", "CMAKE_OBJCOPY"},
    "configure_macos_unwind": {"APPLE"},
}


class SplitError(Exception):
    pass


class Command:
    def __init__(self, name, arguments, first, last):
        self.name = name
        self.arguments = arguments
        self.first = first
        self.last = last


class Block:
    def __init__(self, header):
        self.header = header
        self.branches = [(header, [])]
        self.end = None
        self.first = header.first

    @property
    def last(self):
        return self.end.last


def arguments_of(text, position, line):
    arguments, depth, token = [], 0, None
    while True:
        if position >= len(text):
            raise SplitError(f"line {line + 1}: unterminated command")
        character = text[position]
        if character == "\n":
            line += 1
        if character == '"':
            end = position + 1
            while text[end] != '"':
                if text[end] == "\\":
                    end += 1
                if text[end] == "\n":
                    line += 1
                end += 1
            token = (token or "") + text[position + 1:end]
            position = end + 1
            continue
        bracket = re.match(r"\[(=*)\[", text[position:position + 32])
        if bracket and token is None:
            close = text.index("]" + bracket[1] + "]", position)
            value = text[position + len(bracket[0]):close]
            line += value.count("\n")
            arguments.append(value)
            position = close + len(bracket[0])
            continue
        if character == "#":
            comment = re.match(r"#\[(=*)\[", text[position:position + 32])
            close = text.index("]" + comment[1] + "]", position) + len(comment[1]) + 2 if comment else text.find("\n", position)
            line += text[position:close].count("\n")
            position = close
            continue
        if character == "\\" and token is not None:
            token += text[position:position + 2]
            position += 2
            continue
        if character in " \t\r\n()":
            if token is not None:
                arguments.append(token)
                token = None
            if character == "(":
                depth += 1
                arguments.append("(")
            elif character == ")":
                if depth == 0:
                    return arguments, position + 1, line
                depth -= 1
                arguments.append(")")
            position += 1
            continue
        token = (token or "") + character
        position += 1


def commands(text):
    lines = text.split("\n")
    offsets = [0]
    for item in lines:
        offsets.append(offsets[-1] + len(item) + 1)
    found, index = [], 0
    while index < len(lines):
        stripped = lines[index].strip()
        if not stripped or stripped.startswith("#"):
            index += 1
            continue
        call = CALL.match(lines[index])
        if not call:
            raise SplitError(f"line {index + 1}: not a command: {lines[index]}")
        arguments, end, last = arguments_of(text, offsets[index] + call.end(), index)
        rest = text[end:offsets[last + 1] - 1] if last + 1 < len(offsets) else text[end:]
        if rest.strip() and not rest.strip().startswith("#"):
            raise SplitError(f"line {last + 1}: more than one command on a line")
        found.append(Command(call[1].lower(), arguments, index, last))
        index = last + 1
    return found


def tree(text):
    root, stack = [], []
    for command in commands(text):
        if command.name in OPEN:
            block = Block(command)
            (stack[-1].branches[-1][1] if stack else root).append(block)
            stack.append(block)
        elif command.name in BRANCH:
            if not stack or stack[-1].header.name != "if":
                raise SplitError(f"line {command.first + 1}: {command.name} outside if")
            stack[-1].branches.append((command, []))
        elif command.name in OPEN.values():
            if not stack or OPEN[stack[-1].header.name] != command.name:
                raise SplitError(f"line {command.first + 1}: unmatched {command.name}")
            stack.pop().end = command
        else:
            (stack[-1].branches[-1][1] if stack else root).append(command)
    if stack:
        raise SplitError(f"line {stack[-1].first + 1}: unclosed {stack[-1].header.name}")
    return root


def flatten(node):
    if isinstance(node, Command):
        yield node
        return
    for branch, children in node.branches:
        yield branch
        for child in children:
            yield from flatten(child)
    yield node.end


class Atom:
    def __init__(self, node, conditions):
        self.node = node
        self.conditions = conditions

    def flat(self):
        return flatten(self.node)


def atoms(nodes, conditions=()):
    for node in nodes:
        if isinstance(node, Block) and node.header.name == "if" and len(node.branches) == 1:
            yield from atoms(node.branches[0][1], conditions + (node,))
        else:
            yield Atom(node, conditions)


def enclosing_loop(lines, start):
    depth = 0
    for index in range(start, len(lines)):
        stripped = lines[index].strip()
        if re.match(r"foreach\s*\(", stripped):
            depth += 1
        elif re.match(r"endforeach\s*\(", stripped):
            depth -= 1
            if depth == 0:
                return start, index, len(lines[start]) - len(lines[start].lstrip())
    raise SplitError(f"line {start + 1}: unterminated loop")


def find_loop(lines, predicate, what):
    starts = [index for index, line in enumerate(lines) if predicate(index, line.strip())]
    if len(starts) > 1:
        raise SplitError(f"more than one {what}")
    return enclosing_loop(lines, starts[0]) if starts else None


def dedent(lines, amount):
    return [line[amount:] if line.startswith(" " * amount) else line for line in lines]


def loop_list(header):
    return header[header.index("ITEMS") + len("ITEMS"):header.rindex(")")].split()


def default_tests(lines):
    found = find_loop(lines, lambda index, line: line.startswith("foreach(agcTest IN ITEMS ") and "${agcExecutionTests}" in line,
                      "default-test loop")
    if found is None:
        raise SplitError("the default-test loop over ${agcExecutionTests} is missing")
    start, end, indent = found
    body = lines[start + 1:end]
    skip = []
    if body and body[0].strip().startswith("if(agcTest STREQUAL"):
        close = next(index for index, line in enumerate(body) if line.strip() == "endif()")
        skip, body = body[:close + 1], body[close + 1:]
    kept, tweaks, index = [], [], 0
    while index < len(body):
        special = SPECIAL.fullmatch(body[index].strip())
        if not special:
            kept.append(body[index])
            index += 1
            continue
        depth = len(body[index]) - len(body[index].lstrip())
        close = next(position for position in range(index, len(body))
                     if body[position].strip() == "endif()" and len(body[position]) - len(body[position].lstrip()) == depth)
        inner = body[index + 1:close]
        if not inner or not inner[0].strip().startswith("set_tests_properties(${agcTestName} "):
            raise SplitError(f"line {start + index + 2}: a default-test case does more than set properties")
        tweaks += [" " * indent + line.strip().replace("${agcTestName}", special[1]) if position == 0 else line[8:]
                   for position, line in enumerate(inner)]
        index = close + 1
    pad = " " * indent
    lines[start:end + 1] = [f"{pad}agc_add_default_test({name})" for name in loop_list(lines[start])
                            if name != "${agcExecutionTests}"] + tweaks
    function = ["function(agc_add_default_test agcTest)"] + dedent(kept, indent) + ["endfunction()"]
    execution = ["if(BUILD_TESTING)", "    foreach(agcTest IN LISTS agcExecutionTests)"] + \
        [" " * 8 + line[indent + 4:] for line in skip] + ["        agc_add_default_test(${agcTest})", "    endforeach()", "endif()"]
    return function, execution


def draw_pipeline_tests(lines):
    found = find_loop(lines, lambda index, line: line == "foreach(agcTestName IN LISTS agcDrawPipelineTests)", "draw pipeline loop")
    if found is None:
        return None
    start, end, indent = found
    listing = lines[start - 1].strip()
    if not listing.startswith("set(agcDrawPipelineTests "):
        raise SplitError("agcDrawPipelineTests is not set right before its loop")
    names = listing[len("set(agcDrawPipelineTests "):-1].split()
    body = lines[start + 1:end]
    lines[start - 1:end + 1] = [f"{' ' * indent}agc_add_draw_pipeline_test({name})" for name in names]
    return ["function(agc_add_draw_pipeline_test agcTestName)"] + dedent(body, indent) + ["endfunction()"]


def spirv_mode_tests(lines):
    found = find_loop(lines, lambda index, line: line.startswith("foreach(agcTest IN ITEMS ") and index + 1 < len(lines)
                      and lines[index + 1].strip() == "if(NOT TARGET ${agcTest})", "SPIR-V mode loop")
    if found is None:
        return None
    start, end, indent = found
    body = lines[start + 1:end]
    if body[1].strip() != "continue()":
        raise SplitError("the SPIR-V mode loop no longer starts with its target check")
    body[1] = body[1].replace("continue()", "return()")
    lines[start:end + 1] = [f"{' ' * indent}agc_add_spirv_mode_tests({name})" for name in loop_list(lines[start])]
    return ["function(agc_add_spirv_mode_tests agcTest)"] + dedent(body, indent) + ["endfunction()"]


def refactor(text):
    if "function(agc_add_default_test " in text:
        return text
    lines = text.split("\n")
    function, execution = default_tests(lines)
    functions = [function]
    for convert in (draw_pipeline_tests, spirv_mode_tests):
        function = convert(lines)
        if function:
            functions.append(function)
    glob = [index for index, line in enumerate(lines) if line.startswith("foreach(agcExecutionTestSource IN LISTS agcExecutionTestSources)")]
    if len(glob) != 1:
        raise SplitError("the execution-test loop is missing")
    close = next(index for index in range(glob[0], len(lines)) if lines[index] == "endforeach()")
    added = [""]
    for function in functions:
        added += function + [""]
    lines[close + 1:close + 1] = added + execution + [""]
    return "\n".join(lines)


class Facts:
    def __init__(self):
        self.targets = set()
        self.tests = {}
        self.dynamic_tests = []
        self.subject_targets = set()
        self.subject_tests = set()
        self.test_patterns = set()
        self.dynamic = set()
        self.defines = set()
        self.accumulates = set()
        self.uses = set()
        self.loop = set()
        self.mentions = set()
        self.calls = set()
        self.functions = set()
        self.reads_all_tests = False
        self.creates_defaults = False
        self.dynamic_targets = False


def until(arguments, keywords):
    for index, argument in enumerate(arguments):
        if argument in keywords:
            return arguments[:index]
    return arguments


def literal(name):
    return "${" not in name and "$<" not in name


def subject(facts, names, kind):
    for name in names:
        if literal(name):
            (facts.subject_targets if kind == "target" else facts.subject_tests).add(name)
        else:
            facts.dynamic.update(VARIABLE.findall(name))
            if kind == "test":
                facts.test_patterns.add(name)


def loop_items(atom):
    items = {}
    for command in atom.flat():
        arguments = command.arguments
        if command.name != "foreach" or not arguments:
            continue
        rest = arguments[1:]
        if rest[:1] == ["IN"]:
            if rest[1:2] != ["ITEMS"]:
                continue
            rest = rest[2:]
        elif rest[:1] == ["RANGE"]:
            bounds = rest[1:]
            if not all(bound.isdigit() for bound in bounds) or not 1 <= len(bounds) <= 3:
                continue
            numbers = [int(bound) for bound in bounds]
            start, stop = (0, numbers[0]) if len(numbers) == 1 else (numbers[0], numbers[1])
            rest = [str(value) for value in range(start, stop + 1, numbers[2] if len(numbers) == 3 else 1)]
        if all(literal(item) for item in rest):
            items[arguments[0]] = rest
    return items


def expand(name, items):
    names = [name]
    for variable in set(VARIABLE.findall(name)):
        if variable not in items:
            return []
        names = [candidate.replace("${" + variable + "}", value) for candidate in names for value in items[variable]]
    return names


def facts_of(atom, spec=AGC_SPEC):
    facts = Facts()
    if isinstance(atom.node, Block) and atom.node.header.name in ("function", "macro"):
        facts.functions.add(atom.node.header.arguments[0].lower())
        return facts
    for command in atom.flat():
        arguments, name = command.arguments, command.name
        facts.calls.add(name)
        for argument in arguments:
            facts.uses.update(VARIABLE.findall(argument))
            if "$<" not in argument:
                facts.mentions.update(MENTION.findall(argument))
        if name in ("if", "elseif", "while"):
            facts.uses.update(argument for argument in arguments if IDENT.fullmatch(argument))
        if name == "foreach" and arguments:
            facts.loop.add(arguments[0])
            if "LISTS" in arguments:
                facts.uses.update(argument for argument in arguments[arguments.index("LISTS") + 1:]
                                  if IDENT.fullmatch(argument) and argument != "ITEMS")
        for index, argument in enumerate(arguments[1:-1], 1):
            if argument == "IN_LIST":
                facts.uses.add(arguments[index + 1])
        if name in ("list", "string") and len(arguments) > 1 and arguments[0] in LIST_READERS:
            facts.uses.add(arguments[1])
            facts.accumulates.add(arguments[1])
        if name in SETTERS:
            for index, argument in enumerate(arguments):
                if IDENT.fullmatch(argument) and not (name == "foreach" and index):
                    facts.defines.add(argument)
                if name in ("set", "unset", "option", "foreach"):
                    break
        if name in HELPERS and arguments:
            if literal(arguments[0]):
                executable, tests = HELPERS[name](arguments[0])
                facts.tests.update({test: executable for test in tests})
                if name != "agc_add_draw_pipeline_test":
                    facts.subject_targets.add(arguments[0])
            else:
                facts.dynamic.update(VARIABLE.findall(arguments[0]))
                facts.dynamic_tests.append((arguments[0], None))
                facts.creates_defaults = True
        if name in DEFINERS and arguments:
            if literal(arguments[0]):
                facts.targets.add(arguments[0])
            else:
                facts.dynamic.update(VARIABLE.findall(arguments[0]))
                facts.dynamic_targets = True
        elif name == "add_test" and arguments:
            if arguments[0] == "NAME":
                test = arguments[1]
                rest = until(arguments[2:], TEST_KEYWORDS)
                executable = rest[rest.index("COMMAND") + 1] if "COMMAND" in rest[:-1] else None
            else:
                test, executable = arguments[0], arguments[1] if len(arguments) > 1 else None
            if literal(test):
                facts.tests[test] = executable
            else:
                facts.dynamic_tests.append((test, executable))
        elif name in SUBJECT_FIRST and arguments:
            subject(facts, arguments[:1], "target")
        elif spec.custom_target_commands and name == "add_custom_command" and arguments[:1] == ["TARGET"]:
            subject(facts, arguments[1:2], "target")
        elif name == "add_asan_test_options" and arguments:
            subject(facts, arguments[:1], "test")
        elif name == "set_target_properties":
            subject(facts, until(arguments, {"PROPERTIES"}), "target")
        elif name == "set_tests_properties":
            subject(facts, until(arguments, {"PROPERTIES", "DIRECTORY"}), "test")
        elif name == "set_property" and len(arguments) > 1 and arguments[0] in ("TARGET", "TEST"):
            subject(facts, until(arguments[1:], {"PROPERTY", "APPEND", "APPEND_STRING", "DIRECTORY"}), arguments[0].lower())
        elif name in ("get_target_property", "get_test_property") and len(arguments) > 1:
            subject(facts, arguments[1:2], "target" if name == "get_target_property" else "test")
        elif name == "get_directory_property" and "TESTS" in arguments:
            facts.reads_all_tests = True
        elif name not in CONTROL and name not in HELPERS and arguments and UNIT.fullmatch(arguments[0]):
            subject(facts, arguments[:1], "target")
    items = loop_items(atom)
    for test, executable in facts.dynamic_tests:
        for name in expand(test, items):
            facts.tests.setdefault(name, executable)
    facts.test_patterns = {prefix for prefix in (re.split(r"\$[{<]", name)[0] for name in
                                                 facts.test_patterns - {test for test, _executable in facts.dynamic_tests}) if prefix}
    return facts


def union_find(size):
    parent = list(range(size))

    def find(index):
        while parent[index] != index:
            parent[index] = parent[parent[index]]
            index = parent[index]
        return index

    def join(first, second):
        parent[find(first)] = find(second)

    return find, join


def reads(facts):
    return (facts.uses - (facts.defines - facts.accumulates)) | facts.accumulates


def variable_effects(command):
    arguments, name = command.arguments, command.name
    used = set().union(*(set(VARIABLE.findall(argument)) for argument in arguments))
    written = set()

    def variable(index):
        if not -len(arguments) <= index < len(arguments) or not IDENT.fullmatch(arguments[index]):
            raise SplitError(f"line {command.first + 1}: a computed or unsupported variable binding requires a manual migration")
        return arguments[index]

    def binding(index, read=False):
        output = variable(index)
        written.add(output)
        if read:
            used.add(output)

    def unsupported():
        operation = arguments[0] if arguments else ""
        raise SplitError(f"line {command.first + 1}: unsupported {name}({operation}) effects require a manual migration")

    if name in {"set", "unset", "option", "get_target_property", "get_test_property", "get_directory_property",
                "get_property", "get_filename_component", "separate_arguments"}:
        binding(0, name == "separate_arguments" and len(arguments) == 1)
        if name == "get_directory_property":
            offset = 3 if arguments[1:2] == ["DIRECTORY"] else 1
            if arguments[offset:offset + 1] == ["DEFINITION"]:
                used.add(variable(offset + 1))
    elif name == "math":
        if arguments[:1] != ["EXPR"]:
            unsupported()
        binding(1)
    elif name == "string":
        operation = arguments[0] if arguments else ""
        outputs = {"FIND": 3, "REPLACE": 3, "CONCAT": 1, "JOIN": 2, "TOLOWER": 2, "TOUPPER": 2,
                   "LENGTH": 2, "SUBSTRING": 4, "STRIP": 2, "GENEX_STRIP": 2, "REPEAT": 3, "COMPARE": 4,
                   "HEX": 2, "MAKE_C_IDENTIFIER": 2, "ASCII": -1, "TIMESTAMP": 1, "UUID": 1,
                   "MD5": 1, "SHA1": 1, "SHA224": 1, "SHA256": 1, "SHA384": 1, "SHA512": 1,
                   "SHA3_224": 1, "SHA3_256": 1, "SHA3_384": 1, "SHA3_512": 1}
        if operation in outputs:
            binding(outputs[operation])
        elif operation in {"APPEND", "PREPEND"}:
            binding(1, True)
        elif operation == "REGEX" and arguments[1:2] in (["MATCH"], ["MATCHALL"], ["REPLACE"]):
            binding(4 if arguments[1] == "REPLACE" else 3)
            written.update({"CMAKE_MATCH_COUNT"} | {f"CMAKE_MATCH_{index}" for index in range(10)})
        else:
            unsupported()
    elif name == "list":
        operation = arguments[0] if arguments else ""
        outputs = {"LENGTH": 2, "GET": -1, "JOIN": 3, "SUBLIST": 4, "FIND": 3}
        if len(arguments) < 2 or not IDENT.fullmatch(arguments[1]):
            unsupported()
        used.add(arguments[1])
        if operation in outputs:
            binding(outputs[operation])
        elif operation in {"APPEND", "PREPEND", "INSERT", "REMOVE_ITEM", "REMOVE_AT", "REMOVE_DUPLICATES", "SORT", "REVERSE"}:
            binding(1)
        elif operation in {"POP_BACK", "POP_FRONT"}:
            binding(1)
            for index in range(2, len(arguments)):
                binding(index)
        else:
            unsupported()
    elif name == "file":
        operation = arguments[0] if arguments else ""
        outputs = {"READ": 2, "STRINGS": 2, "TIMESTAMP": 2, "SIZE": 2, "READ_SYMLINK": 2, "REAL_PATH": 2,
                   "RELATIVE_PATH": 1, "TO_CMAKE_PATH": 2, "TO_NATIVE_PATH": 2, "GLOB": 1, "GLOB_RECURSE": 1,
                   "MD5": 2, "SHA1": 2, "SHA224": 2, "SHA256": 2, "SHA384": 2, "SHA512": 2,
                   "SHA3_224": 2, "SHA3_256": 2, "SHA3_384": 2, "SHA3_512": 2}
        if operation in outputs:
            binding(outputs[operation])
            if operation == "STRINGS" and "REGEX" in arguments[3:]:
                written.update({"CMAKE_MATCH_COUNT"} | {f"CMAKE_MATCH_{index}" for index in range(10)})
        elif operation == "MAKE_DIRECTORY":
            if "RESULT" in arguments[1:]:
                binding(arguments.index("RESULT", 1) + 1)
        elif operation not in {"WRITE", "APPEND", "GENERATE", "TOUCH", "TOUCH_NOCREATE", "REMOVE", "REMOVE_RECURSE"}:
            unsupported()
    elif name in STRICT_OPAQUE or name == "set_property" and arguments[:1] not in (["TARGET"], ["TEST"]):
        unsupported()
    elif name in {"if", "elseif", "while"}:
        used.update(argument for argument in arguments if IDENT.fullmatch(argument))
        if "MATCHES" in arguments:
            written.update({"CMAKE_MATCH_COUNT"} | {f"CMAKE_MATCH_{index}" for index in range(10)})
    elif name == "foreach":
        if "ZIP_LISTS" in arguments:
            unsupported()
        if "LISTS" in arguments:
            for variable in arguments[arguments.index("LISTS") + 1:]:
                if variable == "ITEMS":
                    break
                if not IDENT.fullmatch(variable):
                    unsupported()
                used.add(variable)
    elif name in {"block", "return"} and "PROPAGATE" in arguments:
        unsupported()
    return used, written


class Plan:
    def __init__(self, text, execution=(), spec=AGC_SPEC):
        self.spec = spec
        self.lines = text.split("\n")
        self.roots = tree(text)
        if spec.strict:
            self.check_context()
        self.atoms = list(atoms(self.roots))
        self.facts = [facts_of(atom, spec) for atom in self.atoms]
        self.known = {name for facts in self.facts for name in facts.targets | facts.subject_targets | set(facts.tests.values())
                      if name and UNIT.fullmatch(name)} | set(execution)
        self.external = self.known - {name for facts in self.facts for name in facts.targets}
        self.test_units = {test: self.unit_of_test(test, executable) for facts in self.facts for test, executable in facts.tests.items()}
        self.units = self.assign()
        self.include = self.place()
        if spec.strict:
            self.check_order()

    def check_context(self):
        context = {"CMAKE_CURRENT_LIST_DIR", "CMAKE_CURRENT_LIST_FILE", "CMAKE_CURRENT_LIST_LINE", "CMAKE_PARENT_LIST_FILE",
                   "CMAKE_CURRENT_FUNCTION_LIST_DIR", "CMAKE_CURRENT_FUNCTION_LIST_FILE", "CMAKE_CURRENT_FUNCTION_LIST_LINE"}
        functions = set()
        for root in self.roots:
            for command in flatten(root):
                if any(re.search(r"\$(?:ENV|CACHE)?\{[^}]*\$(?:ENV|CACHE)?\{", argument) for argument in command.arguments):
                    raise SplitError(f"line {command.first + 1}: a computed variable reference requires a manual migration")
                used = set().union(*(set(VARIABLE.findall(argument)) for argument in command.arguments))
                if used & context:
                    name = sorted(used & context)[0]
                    raise SplitError(f"line {command.first + 1}: list context {name} requires a manual migration")
                arguments = command.arguments
                if command.name == "function":
                    name = arguments[0].lower() if arguments else ""
                    if not name or not literal(name) or name in functions:
                        raise SplitError(f"line {command.first + 1}: a computed or repeated helper definition requires a manual migration")
                    functions.add(name)
                cache_set = command.name == "set" and (arguments[:1] and arguments[0].startswith("CACHE{")
                            or len(arguments) >= 4 and arguments[-3] == "CACHE"
                            or len(arguments) >= 5 and arguments[-1] == "FORCE" and arguments[-4] == "CACHE")
                scope_set = command.name in {"set", "unset"} and arguments[-1:] == ["PARENT_SCOPE"]
                cache_unset = command.name == "unset" and arguments[-1:] == ["CACHE"]
                cache_property = command.name == "set_property" and arguments[:1] == ["CACHE"]
                cache_component = command.name == "get_filename_component" and arguments[-1:] == ["CACHE"]
                if command.name == "macro" or cache_set or scope_set or cache_unset or cache_property or cache_component:
                    raise SplitError(f"line {command.first + 1}: macro, parent-scope or cache effects require a manual migration")
                if (command.name in STRICT_OPAQUE
                        or command.name == "set_property" and arguments[:1] not in (["TARGET"], ["TEST"])
                        or command.name in {"block", "return"} and "PROPAGATE" in arguments
                        or command.name == "foreach" and "ZIP_LISTS" in arguments):
                    variable_effects(command)

    def check_order(self):
        top = [next(index for index, root in enumerate(self.roots) if root.first <= atom.node.first <= root.last)
               for atom in self.atoms]
        order = [index for index, unit in enumerate(self.units) if not unit and top[index] < self.include]
        for unit in sorted(set(filter(None, self.units))):
            order.extend(index for index, owner in enumerate(self.units) if owner == unit)
        order.extend(index for index, unit in enumerate(self.units) if not unit and top[index] >= self.include)
        position = {atom: index for index, atom in enumerate(order)}
        functions = {atom.node.header.arguments[0].lower(): atom.node for atom in self.atoms
                     if isinstance(atom.node, Block) and atom.node.header.name == "function"}
        commands = [[condition.header for condition in atom.conditions]
                    + ([] if isinstance(atom.node, Block) and atom.node.header.name == "function" else list(atom.flat()))
                    for atom in self.atoms]
        effects = {command: variable_effects(command) for calls in commands for command in calls}
        initializers = {name for _used, written in effects.values() for name in written if name.startswith("CMAKE_")}
        target_calls = DEFINERS | SUBJECT_FIRST | set(HELPERS) | set(functions) | {"configure_host_test_executable"}
        function_reads, function_calls, parameters = {}, {}, {}
        for name, node in functions.items():
            function_reads[name], function_calls[name] = set(), set()
            parameters[name] = set(node.header.arguments[1:])
            for command in flatten(node):
                if command is node.header or command is node.end:
                    continue
                if (command.name == "function" or command.name in {"get_target_property", "get_test_property"}
                        or command.name == "get_property" and command.arguments[1:2] in (["TARGET"], ["TEST"])
                        or command.name in {"if", "elseif", "while"} and {"TARGET", "TEST"} & set(command.arguments)):
                    raise SplitError(f"line {command.first + 1}: helper scope or target introspection requires a manual migration")
                command_used, _written = variable_effects(command)
                function_reads[name] |= command_used
                function_reads[name].update(KERNEL_HELPER_READS.get(command.name, ()))
                if command.name in target_calls:
                    function_reads[name] |= initializers
                if command.name in functions:
                    function_calls[name].add(command.name)
            function_reads[name] -= parameters[name]
            function_reads[name] = {variable for variable in function_reads[name] if not re.fullmatch(r"ARG[CVN]|ARGV[0-9]*", variable)}
        while True:
            fresh = {name: (used | set().union(*(function_reads[callee] for callee in function_calls[name]))) - parameters[name]
                     for name, used in function_reads.items()}
            if fresh == function_reads:
                break
            function_reads = fresh
        definitions, readers, targets, tests = {}, {}, {}, {}

        def preserve(first, last, reason):
            if first != last and position[first] > position[last]:
                begin = self.atoms[first].node.first + 1
                end = self.atoms[last].node.first + 1
                raise SplitError(f"cannot preserve {reason} order between lines {begin} and {end}; migrate the dependent registrations by hand")

        for index, facts in enumerate(self.facts):
            for target in facts.targets:
                targets.setdefault(target, []).append(index)
            for test in facts.tests:
                tests.setdefault(test, []).append(index)
        for index, (atom, facts) in enumerate(zip(self.atoms, self.facts)):
            used, written = set(), set()
            referenced_targets = facts.subject_targets - facts.targets
            referenced_tests = facts.subject_tests - set(facts.tests)
            for command in commands[index]:
                command_used, command_written = effects[command]
                used |= command_used
                used |= function_reads.get(command.name, set())
                used.update(KERNEL_HELPER_READS.get(command.name, ()))
                if command.name in target_calls:
                    used |= initializers
                written |= command_written
                if command.name == "get_property" and command.arguments[1:2] in (["TARGET"], ["TEST"]):
                    name = command.arguments[2] if len(command.arguments) > 2 else ""
                    if not name or not literal(name):
                        raise SplitError(f"line {command.first + 1}: a computed property subject requires a manual migration")
                    (referenced_targets if command.arguments[1] == "TARGET" else referenced_tests).add(name)
                if command.name not in {"if", "elseif", "while"}:
                    continue
                arguments = command.arguments
                for offset, keyword in enumerate(arguments[:-1]):
                    if keyword not in ("TARGET", "TEST"):
                        continue
                    name = arguments[offset + 1]
                    if not literal(name):
                        raise SplitError(f"line {command.first + 1}: a computed {keyword.lower()} condition requires a manual migration")
                    (referenced_targets if keyword == "TARGET" else referenced_tests).add(name)
            for name in used - facts.loop:
                if name in definitions:
                    preserve(definitions[name], index, f"variable {name}")
                readers.setdefault(name, set()).add(index)
            for name in written - facts.loop:
                if name in definitions:
                    preserve(definitions[name], index, f"variable {name}")
                for reader in readers.get(name, ()):
                    preserve(reader, index, f"variable {name}")
                readers[name] = set()
                definitions[name] = index
            for referenced, owners, kind in ((referenced_targets, targets, "target"), (referenced_tests, tests, "test")):
                for name in referenced:
                    for owner in owners.get(name, ()):
                        preserve(min(owner, index), max(owner, index), f"{kind} {name}")

    def unit_of_test_name(self, test):
        stems = [unit for unit in self.known if test == unit[:-6] or test.startswith(unit[:-6] + "_")]
        return max(stems, key=len) if stems else None

    def unit_of_test(self, test, executable):
        return executable if executable and literal(executable) and UNIT.fullmatch(executable) else self.unit_of_test_name(test)

    def candidates(self, index, test_owner):
        facts = self.facts[index]
        owners, unknown = set(), False
        for target in facts.targets | facts.subject_targets:
            if UNIT.fullmatch(target):
                owners.add(target)
            else:
                unknown = True
        for test, executable in facts.tests.items():
            owner = self.unit_of_test(test, executable)
            if owner:
                owners.add(owner)
        for test in facts.subject_tests - set(facts.tests):
            if test in test_owner:
                owners.add(test_owner[test])
            elif test + "_tests" in self.external:
                owners.add(test + "_tests")
            else:
                unknown = True
        for prefix in facts.test_patterns:
            matched = {unit for test, unit in self.test_units.items() if test.startswith(prefix)}
            if len(matched) == 1 and None not in matched:
                owners |= matched
            elif matched:
                unknown = True
        if facts.dynamic - facts.defines or facts.reads_all_tests or facts.creates_defaults or facts.dynamic_targets:
            unknown = True
        if facts.dynamic or facts.dynamic_tests:
            for _test, executable in facts.dynamic_tests:
                if executable and literal(executable) and UNIT.fullmatch(executable):
                    owners.add(executable)
            if facts.dynamic and len(facts.mentions | owners) > 1:
                unknown = True
            owners |= facts.mentions
        return owners, unknown

    def write_groups(self):
        defining = {}
        for index, facts in enumerate(self.facts):
            for name in facts.defines:
                defining.setdefault(name, []).append(index)
        mutable = {name for name, indices in defining.items() if len(indices) > 1}
        mutable |= set().union(*(facts.accumulates for facts in self.facts))
        find, join = union_find(len(self.atoms))
        for index, facts in enumerate(self.facts):
            for name in reads(facts) & mutable & facts.defines:
                for earlier in reversed([other for other in defining[name] if other < index]):
                    join(earlier, index)
                    if name in self.facts[earlier].defines - self.facts[earlier].accumulates:
                        break
        return [find(index) for index in range(len(self.atoms))]

    def variable_components(self, free):
        defining = {}
        find, join = union_find(len(self.atoms))
        for index, facts in enumerate(self.facts):
            for name in reads(facts):
                for earlier in reversed(defining.get(name, [])):
                    if free[earlier] or free[index]:
                        join(earlier, index)
                    if name in self.facts[earlier].defines - self.facts[earlier].accumulates:
                        break
            for name in facts.defines - facts.loop:
                defining.setdefault(name, []).append(index)
        components = {}
        for index in range(len(self.atoms)):
            components.setdefault(find(index), []).append(index)
        return [indices for indices in components.values() if any(free[index] for index in indices)]

    def assign(self):
        group = self.write_groups()
        members = {}
        for index in range(len(self.atoms)):
            members.setdefault(group[index], []).append(index)
        test_owner, pinned = {}, set()
        while True:
            units, unknowns = [], []
            for index in range(len(self.atoms)):
                owners, unknown = self.candidates(index, test_owner)
                units.append(owners)
                unknowns.append(unknown or group[index] in pinned)
            fresh_pinned = set(pinned)
            for root, indices in members.items():
                if len(indices) > 1 and any(unknowns[index] for index in indices) and any(units[index] for index in indices):
                    fresh_pinned.add(root)
            result = []
            for index in range(len(self.atoms)):
                if unknowns[index] or group[index] in fresh_pinned:
                    result.append(None)
                else:
                    result.append(set().union(*(units[other] for other in members[group[index]])) or None)
            first = min((index for index in range(len(self.atoms)) if result[index]), default=len(self.atoms))
            free = [not result[index] and not unknowns[index] and not units[index] and index > first
                    and group[index] not in fresh_pinned for index in range(len(self.atoms))]
            for indices in self.variable_components(free):
                if any(not free[index] and not result[index] for index in indices):
                    continue
                owners = {frozenset(result[index]) for index in indices if result[index]}
                if len(owners) == 1:
                    for index in indices:
                        if free[index]:
                            result[index] = set(next(iter(owners)))
            fresh = {}
            for index, owners in enumerate(result):
                if owners and len(owners) == 1:
                    for test in self.facts[index].tests:
                        fresh[test] = next(iter(owners))
            if fresh == test_owner and fresh_pinned == pinned:
                break
            test_owner, pinned = fresh, fresh_pinned
        names = sorted({name for owners in result if owners for name in owners})
        position = {name: index for index, name in enumerate(names)}
        find, join = union_find(len(names))
        sizes = {}
        for index, owners in enumerate(result):
            if not owners:
                continue
            ordered = sorted(owners)
            for name in ordered:
                join(position[name], position[ordered[0]])
                sizes[name] = sizes.get(name, 0) + self.atoms[index].node.last - self.atoms[index].node.first + 1
        largest = {}
        for name in names:
            root = find(position[name])
            if root not in largest or (sizes[name], name) > (sizes[largest[root]], largest[root]):
                largest[root] = name
        return [largest[find(position[next(iter(owners))])] if owners else None for owners in result]

    def place(self):
        moved = [index for index, unit in enumerate(self.units) if unit]
        if not moved:
            raise SplitError(f"{self.spec.lists} registers no tests to move")

        def union(field):
            return set().union(*(getattr(self.facts[index], field) for index in moved))

        defined, used, targets, calls = union("defines"), union("uses"), union("targets"), union("calls")
        tests = set().union(*(set(self.facts[index].tests) for index in moved))
        everywhere = set().union(*(facts.targets for facts in self.facts))
        external = {name for name in union("subject_targets") if UNIT.fullmatch(name) and name not in everywhere}
        needed, depends = [], []
        for index, facts in enumerate(self.facts):
            if self.units[index]:
                continue
            if ((facts.defines - facts.loop) & used or (facts.dynamic_targets and external) or facts.creates_defaults
                    or facts.functions & calls):
                needed.append(index)
            if ((facts.uses - facts.defines) & defined or facts.subject_targets & targets or facts.subject_tests & tests
                    or facts.mentions & targets or facts.reads_all_tests
                    or any(test.startswith(prefix) for prefix in facts.test_patterns for test in tests)):
                depends.append(index)
        top = [next(position for position, node in enumerate(self.roots) if node.first <= atom.node.first <= node.last)
               for atom in self.atoms]
        low = top[max(needed)] + 1 if needed else 0
        high = top[min(depends)] if depends else len(self.roots)
        if low > high:
            raise SplitError(f"no single place to include the fragments: line {self.atoms[max(needed)].node.first + 1} must come "
                             f"before them and line {self.atoms[min(depends)].node.first + 1} after them")
        return max(low, min(high, max(top[index] for index in moved) + 1))


def leading(lines, first):
    while first > 0 and lines[first - 1].lstrip().startswith("#"):
        first -= 1
    return first


def opener(line):
    call = CALL.match(line)
    return bool(call) and (call[1].lower() in OPEN or call[1].lower() in BRANCH)


def closer(line):
    call = CALL.match(line)
    return bool(call) and (call[1].lower() in OPEN.values() or call[1].lower() in BRANCH)


def wrappers(nodes):
    for node in nodes:
        if isinstance(node, Block):
            for _branch, children in node.branches:
                yield from wrappers(children)
            yield node


def fragment_text(lines, members):
    out, stack = [], []
    for atom in members:
        conditions = list(atom.conditions)
        common = 0
        while common < min(len(stack), len(conditions)) and stack[common] is conditions[common]:
            common += 1
        while len(stack) > common:
            block = stack.pop()
            out.extend(lines[block.end.first:block.end.last + 1])
        first = leading(lines, atom.node.first)
        separated = first > 0 and not lines[first - 1].strip()
        for block in conditions[common:]:
            if out and not stack and out[-1].strip():
                out.append("")
            out.extend(lines[block.header.first:block.header.last + 1])
            stack.append(block)
        if out and separated and out[-1].strip() and not opener(out[-1]):
            out.append("")
        out.extend(line for line in lines[first:atom.node.last + 1] if not line.lstrip().startswith("#"))
    while stack:
        block = stack.pop()
        out.extend(lines[block.end.first:block.end.last + 1])
    return "\n".join(out) + "\n"


def split_text(text, execution=(), spec=AGC_SPEC):
    plan = Plan(text, execution, spec)
    lines = plan.lines
    units = {}
    for atom, unit in zip(plan.atoms, plan.units):
        if unit:
            units.setdefault(unit, []).append(atom)
    deleted = set()
    for members in units.values():
        for atom in members:
            deleted.update(range(leading(lines, atom.node.first), atom.node.last + 1))
    for block in wrappers(plan.roots):
        if block.header.name != "if" or len(block.branches) != 1:
            continue
        body = range(block.header.last + 1, block.end.first)
        if all(index in deleted or not lines[index].strip() or lines[index].lstrip().startswith("#") for index in body):
            deleted.update(range(leading(lines, block.header.first), block.end.last + 1))
    at = leading(lines, plan.roots[plan.include].first) if plan.include < len(plan.roots) else len(lines)
    kept = []
    for index, line in enumerate(lines):
        if index == at:
            kept.extend([""] + spec.include + [""])
        if index not in deleted:
            kept.append(line)
    if at >= len(lines):
        kept.extend([""] + spec.include)
    residual = []
    for line in kept:
        if not line.strip() and (not residual or not residual[-1].strip() or opener(residual[-1])):
            continue
        if closer(line) and residual and not residual[-1].strip():
            residual.pop()
        residual.append(line)
    while residual and not residual[-1].strip():
        residual.pop()
    return "\n".join(residual) + "\n", {name: fragment_text(lines, members) for name, members in units.items()}


def migrated(text, execution=(), spec=AGC_SPEC):
    return split_text(refactor(text) if spec.execution else text, execution, spec)


def execution_target(stem):
    return "agc_driver_" + re.sub(r"([a-z0-9])([A-Z])", r"\1_\2", stem).lower() + "_tests"


def execution_targets(root, spec=AGC_SPEC):
    return sorted(execution_target(path.stem) for path in (root / spec.execution).glob("*.cpp")) if spec.execution else []


def known_targets(root, spec=AGC_SPEC):
    known = set(execution_targets(root, spec)) | {path.stem for path in (root / spec.fragments).glob("*.cmake")}
    if not spec.execution:
        return sorted(known)
    revisions = ["HEAD"]
    for head in ("REBASE_HEAD", "CHERRY_PICK_HEAD", "MERGE_HEAD"):
        if git(root, "rev-parse", "-q", "--verify", head, check=False).strip():
            revisions += [head, head + "^", git(root, "merge-base", "HEAD", head, check=False).strip()]
    for revision in filter(None, revisions):
        listing = git(root, "ls-tree", "--name-only", f"{revision}:{spec.execution}", check=False)
        known |= {execution_target(Path(name).stem) for name in listing.splitlines() if name.endswith(".cpp")}
    return sorted(known)


def is_split(text, spec=AGC_SPEC):
    return spec.include[0] in text


def git(root, *args, check=True):
    return subprocess.run(["git", *args], cwd=root, capture_output=True, text=True, encoding="utf-8", errors="replace",
                          check=check).stdout


def write_lf(path, text):
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="\n") as file:
        file.write(text)


def fragment_path(name, spec=AGC_SPEC):
    return f"{spec.fragments}/{name}.cmake"


def command_refactor(root, spec=AGC_SPEC):
    if not spec.execution:
        raise SplitError(f"{spec.library} has no registration loops to refactor")
    text = (root / spec.lists).read_text(encoding="utf-8")
    changed = refactor(text)
    if changed == text:
        sys.exit(f"{spec.lists} already registers its default tests through agc_add_default_test")
    write_lf(root / spec.lists, changed)
    print(spec.lists)


def command_split(root, spec=AGC_SPEC):
    text = (root / spec.lists).read_text(encoding="utf-8")
    if is_split(text, spec):
        sys.exit(f"{spec.lists} already includes {spec.fragments}")
    lists, fragments = migrated(text, execution_targets(root, spec), spec)
    existing = sorted(set(fragments) & {path.stem for path in (root / spec.fragments).glob("*.cmake")})
    if existing:
        sys.exit(f"{spec.fragments} already has {', '.join(name + '.cmake' for name in existing)}")
    for name, body in fragments.items():
        write_lf(root / fragment_path(name, spec), body)
    write_lf(root / spec.lists, lists)
    print(f"{len(fragments)} fragments in {spec.fragments}, {len(lists.splitlines())} lines left in {spec.lists}")


def merge(base, ours, theirs, label):
    if base == theirs:
        return ours, False
    if base == ours:
        return theirs, False
    with tempfile.TemporaryDirectory() as directory:
        paths = []
        for name, text in (("ours", ours), ("base", base), ("theirs", theirs)):
            write_lf(Path(directory) / name, text)
            paths.append(str(Path(directory) / name))
        result = subprocess.run(["git", "merge-file", "-p", "-L", f"{label} (split)", "-L", "before the split",
                                 "-L", f"{label} (change)", *paths], capture_output=True, text=True, encoding="utf-8")
    if not 0 <= result.returncode < 128:
        raise SplitError(f"git merge-file failed on {label}")
    return result.stdout, result.returncode > 0


def apply_change(base, change, lists, read, execution=(), spec=AGC_SPEC):
    base_lists, base_fragments = migrated(base, execution, spec)
    change_lists, change_fragments = migrated(change, execution, spec)
    written, conflicted = {}, []
    merged, clash = merge(base_lists, lists, change_lists, spec.lists)
    if merged != lists:
        written[spec.lists] = merged
    if clash:
        conflicted.append(spec.lists)
    for name in sorted(set(base_fragments) | set(change_fragments)):
        before, after = base_fragments.get(name, ""), change_fragments.get(name, "")
        if before == after:
            continue
        path = fragment_path(name, spec)
        merged, clash = merge(before, read(path), after, path)
        written[path] = merged
        if clash:
            conflicted.append(path)
    return written, conflicted


def conflict_marker_size(root, path):
    attribute = git(root, "check-attr", "-z", "conflict-marker-size", "--", path).split("\0")
    if len(attribute) < 3:
        raise SplitError(f"cannot determine Git's conflict marker size for {path}; preserve it and resolve it by hand")
    value = attribute[2]
    return int(value) if value.isdigit() and int(value) > 0 else 7


def conflict_matches(current, expected, marker_size, labels):
    actual_lines, expected_lines = current.splitlines(keepends=True), expected.splitlines(keepends=True)
    if len(actual_lines) != len(expected_lines):
        return False
    markers = {character * marker_size + " " + label: character * marker_size for character, label in zip("<|>", labels)}
    for actual, wanted in zip(actual_lines, expected_lines):
        marker = markers.get(wanted.removesuffix("\n"))
        if marker:
            if actual.endswith("\n") != wanted.endswith("\n"):
                return False
            content = actual.removesuffix("\n")
            if content != marker and not content.startswith(marker + " "):
                return False
        elif actual != wanted:
            return False
    return True


def check_parent_conflict(root, path, base, ours, theirs):
    current = (root / path).read_text(encoding="utf-8")
    marker_size = conflict_marker_size(root, path)
    sentinel = "anyps5-resolver-conflict"
    while any(sentinel in text for text in (base, ours, theirs, current)):
        sentinel += "_"
    labels = tuple(sentinel + " " + side for side in ("ours", "base", "theirs"))
    with tempfile.TemporaryDirectory() as directory:
        paths = []
        for name, text in (("ours", ours), ("base", base), ("theirs", theirs)):
            file = Path(directory) / name
            write_lf(file, text)
            paths.append(str(file))
        for style in ("merge", "diff3", "zdiff3"):
            result = subprocess.run(["git", "-c", f"merge.conflictStyle={style}", "merge-file", "-p",
                                     f"--marker-size={marker_size}", "-L", labels[0], "-L", labels[1], "-L", labels[2], *paths],
                                    cwd=root, capture_output=True, text=True, encoding="utf-8")
            if not 0 <= result.returncode < 128:
                raise SplitError(f"cannot reconstruct Git's conflict for {path}; preserve it and resolve it by hand")
            if conflict_matches(current, result.stdout, marker_size, labels):
                return
    raise SplitError(f"{path} has working-tree edits to Git's conflict result; preserve those edits and resolve it by hand")


def check_fragment_worktree(root, path):
    indexed = git(root, "ls-files", "--stage", "--", path).strip()
    file = root / path
    if not indexed:
        different = file.exists() or file.is_symlink()
    else:
        mode, blob, _stage = indexed.split("\t", 1)[0].split()
        if mode not in ("100644", "100755") or file.is_symlink():
            raise SplitError(f"{path} is not a regular indexed fragment; preserve it and resolve it by hand")
        current = git(root, "hash-object", f"--path={path}", "--", path).strip() if file.exists() else None
        different = current != blob
    if different:
        raise SplitError(f"{path} has different index and working-tree contents; preserve or stage those changes before running resolve")
    status = git(root, "ls-files", "-v", "-z", "--", path)
    if status and status[0] != "H":
        raise SplitError(f"{path} has index flags that prevent safe staging; clear assume-unchanged or skip-worktree before running resolve")
    if indexed and git(root, "config", "--bool", "--get", "core.filemode", check=False).strip() != "false":
        if bool(file.stat().st_mode & 0o100) != (mode == "100755"):
            raise SplitError(f"{path} has different index and working-tree modes; preserve or stage those changes before running resolve")


def command_resolve(root, spec=AGC_SPEC):
    stages = {}
    for line in git(root, "ls-files", "-u", "--", spec.lists).splitlines():
        meta, _ = line.split("\t", 1)
        _, sha, stage = meta.split()
        stages[stage] = sha
    if not {"1", "2", "3"} <= set(stages):
        sys.exit(f"{spec.lists} is not in a three-way conflict")
    base, ours, theirs = (git(root, "cat-file", "-p", stages[stage]) for stage in "123")
    if is_split(base, spec) or is_split(ours, spec) == is_split(theirs, spec):
        sys.exit(f"{spec.lists}: the conflict is not between a change made before the split and the split; resolve it by hand")
    lists, change = (ours, theirs) if is_split(ours, spec) else (theirs, ours)

    def read(path):
        file = root / path
        text = file.read_text(encoding="utf-8") if file.exists() else ""
        size = min(7, conflict_marker_size(root, path))
        if re.search(rf"(?m)^(?:<{{{size},}}|\|{{{size},}}|={{{size},}}|>{{{size},}})(?:[ \t]|$)", text):
            raise SplitError(f"{path} contains conflict markers; preserve it and resolve it by hand")
        check_fragment_worktree(root, path)
        return text

    try:
        unmerged = sorted(filter(None, git(root, "diff", "--name-only", "--diff-filter=U", "-z", "--", spec.fragments).split("\0")))
        if unmerged:
            raise SplitError("unresolved fragment conflicts in " + ", ".join(unmerged) + "; resolve and stage them before running resolve")
        check_parent_conflict(root, spec.lists, base, ours, theirs)
        written, conflicted = apply_change(base, change, lists, read, known_targets(root, spec), spec)
    except (SplitError, OSError, subprocess.CalledProcessError) as error:
        sys.exit(f"{spec.lists}: {error}")
    written.setdefault(spec.lists, lists)
    for path, text in written.items():
        if text.strip():
            write_lf(root / path, text)
        elif (root / path).exists():
            (root / path).unlink()
    clean = [path for path in written if path not in conflicted]
    if clean:
        git(root, "add", "-A", "--", *clean)
    print("\n".join(sorted(written)))
    if conflicted:
        sys.exit("resolve the conflict markers in " + ", ".join(conflicted) + ", then git add them")


def main(argv=None):
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(description="Move library test registrations into fragments per test executable, "
                                                 "and move registrations of a change made before the split")
    parser.add_argument("command", choices=("refactor", "split", "resolve"),
                        help="refactor: convert the AGC registration loops into functions; "
                             "split: move the selected library's test registrations into its tests/cmake/ fragments; "
                             "resolve: during a rebase or merge stopped on that library's CMakeLists.txt, "
                             "apply the change's registrations to the fragments and stage them")
    parser.add_argument("--library", choices=("libSceAgcDriver", "libkernel"), default="libSceAgcDriver",
                        help="library to migrate (default: libSceAgcDriver)")
    args = parser.parse_args(argv)
    spec = KERNEL_SPEC if args.library == "libkernel" else AGC_SPEC
    root = Path(git(Path.cwd(), "rev-parse", "--show-toplevel").strip())
    try:
        {"refactor": command_refactor, "split": command_split, "resolve": command_resolve}[args.command](root, spec)
    except SplitError as error:
        sys.exit(f"{spec.lists}: {error}")


if __name__ == "__main__":
    main()
