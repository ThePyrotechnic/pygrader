import re
import os
import pathlib
import subprocess
import signal
import json
from numbers import Real
from typing import List, Optional, Pattern

import attr
import toml

# from lib.canvas_api import User
from lib.canvas_api import utils

from lib.core.choices import choose, choose_float


# noinspection PyDataclass,PyUnresolvedReferences
@attr.s(auto_attribs=True)
class AssignmentTest:
    """
    An abstract test to be run on an assignment submission
    TODO 'sequential' command requirement

    :param command: The command to be run.
    :param args: List of arguments to pass to the command. Use %s to denote a file name
    :param test_must_pass: If this is true, then no subsequent tests will run if this one fails.
    :param input_str: String to send to stdin
    :param target_file: The file to replace %s with
    :param output_match: An exact string that the output should match. If this and output_regex are None, then this Command always 'matches'
    :param output_regex: A regular expression that the string should match. Combines with output_match.
    If this and output_match are None, then this Command always 'matches'
    :param numeric_match: Enables numeric matching. This overrides string and regex matching
    :param timeout: Time, in seconds, that this Command should run for before timing out
    :param fail_comment: Comment to be appended to the submission if the test fails
    :param point_val: Amount of points that a successful match is worth (Can be negative)
    :param print_file: Whether to print the contents of the target_file being tested (Does nothing if no file is selected)
    :param single_file: Whether to assume the assignment is a single file and use the first file found as %s
    :param ask_for_target: Whether to prompt for a file in the current directory. Overrides file_target
    :param include_filetype: Whether to include the filetype in the %s substitution
    :param print_output: Whether to visibly print the output
    :param negate_match: Whether to negate the result of checking output_match and output_regex
    :param exact_match: Whether the naive string match (output_match) should be an exact check or a substring check
    """

    command: str
    args: List[str] = attr.Factory(list)
    input_str: Optional[str] = None
    target_file: Optional[str] = None
    output_match: Optional[str] = None
    output_regex: Optional[Pattern] = None
    numeric_match: Optional[List] = None
    timeout: Optional[int] = None
    fail_comment: Optional[str] = None
    point_val: float = 0.0

    test_must_pass: bool = False
    print_file: bool = False
    single_file: bool = False
    ask_for_target: bool = False
    include_filetype: bool = True
    print_output: bool = True
    negate_match: bool = False
    exact_match: bool = False
    prompt_for_score: bool = False

    # The name of the test case
    name: Optional[str] = None

    def __attrs_post_init__(self):
        if self.output_regex is not None:
            self.output_regex = re.compile(re.escape(self.output_regex))

    @classmethod
    def from_json_dict(cls, json_dict: dict):
        if "command" not in json_dict:
            return None

        json_dict["input_str"] = json_dict.pop("input", None)
        json_dict["fail_comment"] = json_dict.pop("fail_comment", None)

        return AssignmentTest(**json_dict)

    @classmethod
    def target_prompt(cls, command: str):
        path = pathlib.Path.cwd()
        files = [file for file in path.iterdir() if file.is_file()]

        if not files:
            print(
                f'This directory is empty, unable to choose a file for the "{command}" command'
            )
            return None

        choice = choose(files, 'Select a file for the "%s" command:' % command)
        return choice.name

    def run(self, user: "User") -> dict:
        """
        Runs the Command
        :return: A dictionary containing the command's return code, stdout, timeout
        """
        command = self.command
        args = self.args
        filename = self.target_file
        files = os.listdir(os.getcwd())

        if filename is None:
            if (self.single_file and files) or len(files) == 1:
                filename = files[0]
            elif self.ask_for_target:
                filename = AssignmentTest.target_prompt(self.command)

        if not self.include_filetype and filename is not None:
            filename = os.path.splitext(filename)[0]
        if filename is not None:
            if self.print_file:
                print("--FILE--", file=user.log)
                with open(filename, "r") as f:
                    print(f.read(), file=user.log)
                print("--END FILE--", file=user.log)
            command = self.command.replace("%s", filename)
            args = [arg.replace("%s", filename) for arg in args]

        command_to_send = [command] + args if args else command

        try:
            if os.name == "nt":
                proc = subprocess.run(
                    command_to_send,
                    input=self.input_str,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.STDOUT,
                    timeout=self.timeout,
                    shell=True,
                    encoding="UTF-8",
                )
                stdout = proc.stdout
            else:
                proc = subprocess.Popen(
                    command_to_send,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.STDOUT,
                    shell=True,
                    preexec_fn=os.setsid,
                    encoding="UTF-8",
                )
                stdout, _ = proc.communicate(input=self.input_str, timeout=self.timeout)

        except subprocess.TimeoutExpired:
            if os.name == "nt":
                proc.kill()
            else:
                os.killpg(os.getpgid(proc.pid), signal.SIGTERM)
            return {"timeout": True}

        return {"returncode": proc.returncode, "stdout": stdout, "timeout": False}

    def run_and_match(self, user: "User") -> bool:
        """
        Runs the command and matches the output to the output_match/regex. If
        neither are defined then this always returns true

        :return: Whether the output matched or not
        """
        result = self.run(user)

        if result.get("timeout"):
            return False

        if self.print_output:
            print("\t--OUTPUT--", file=user.log)
            print(result["stdout"], file=user.log)
            print("\n\t--END OUTPUT--", file=user.log)
        if not any((self.output_match, self.output_regex, self.numeric_match)):
            return True

        if self.numeric_match is not None:
            numeric_match = self.numeric_match.copy()
            extracted_nums = map(float, re.findall(utils.NUM_REGEX, result["stdout"]))

            for number in extracted_nums:
                for num in numeric_match:
                    if isinstance(num, str):
                        numeric_match.remove(num)
                        try:
                            center, diff = (
                                float(x) for x in re.findall(utils.NUM_REGEX, num)
                            )
                        except:
                            continue
                        num = [center - diff, center + diff]
                        numeric_match.append(num)
                    if isinstance(num, list):
                        low, high = num
                        if low <= number <= high:
                            numeric_match.remove(num)
                    elif isinstance(num, Real):
                        if number == num:
                            numeric_match.remove(num)

            return len(numeric_match) == 0

        if self.output_regex:
            if self.output_regex.match(result["stdout"]):
                print("--Matched regular expression--", file=user.log)
                if self.negate_match:
                    return False
                return True

        if self.output_match:
            if self.exact_match:
                condition = self.output_match == result["stdout"]
            else:
                condition = self.output_match in result["stdout"]

            if condition:
                print("--Matched string comparison--", file=user.log)
                if self.negate_match:
                    return False
                return True

        return self.negate_match

    def to_json(self):
        """
        Encode an AssignmentTest object as a JSON-compatible dictionary.
        """
        attributes = attr.asdict(self)
        if self.output_regex:
            attributes["output_regex"] = self.output_regex.pattern
        return attributes


@attr.s(auto_attribs=True)
class TestSkeleton:
    """
    An abstract skeleton to handle testing of a specific group of files
    """

    descriptor: str
    tests: List[AssignmentTest]  # Tests to run in the order that they are added.
    disarm: bool = False  # Whether to actually submit grades/send messages
    file_path: str = ""

    @classmethod
    def parse_skeleton(cls, filepath) -> "TestSkeleton":
        """
        Parse a single TestSkeleton
        :return: The parsed skeleton, or None if parsing failed
        """
        return cls.from_file(filepath)

    @classmethod
    def parse_skeletons(cls, directory=None) -> list:
        """
        Responsible for validating and parsing skeleton files
        "param directory: The directory to parse. If none, use current directory.
        :return: A list of valid skeletons
        """

        directory = directory or os.getcwd()
        os.chdir(directory)
        skeleton_list = []
        for skeleton_file in os.listdir(directory):
            skeleton = cls.parse_skeleton(os.path.join(directory, skeleton_file))
            if skeleton is not None:
                skeleton_list.append(skeleton)
        return skeleton_list

    @classmethod
    def from_file(cls, file_path) -> Optional["TestSkeleton"]:
        try:
            with open(file_path) as skeleton_file:
                try:
                    if file_path.endswith(".json"):
                        data = json.load(skeleton_file)
                    elif file_path.endswith(".toml"):
                        data = toml.load(skeleton_file)
                    else:
                        return None
                except (json.JSONDecodeError, toml.TomlDecodeError) as e:
                    print(
                        "There is an error in the",
                        file_path,
                        "skeleton file. This skeleton will not be available",
                    )
                    print("Error:", e)
                    return None
                try:
                    descriptor = data["descriptor"]
                    tests = data["tests"]
                except KeyError:
                    return None
                else:
                    disarm = data.get("disarm", False)
                    defaults = data.get("default", {})
                    test_list = []
                    for name, json_dict in tests.items():
                        args = {**defaults, **json_dict, "name": name}
                        test = AssignmentTest.from_json_dict(args)
                        if test is not None:
                            test_list.append(test)

                    return TestSkeleton(descriptor, test_list, disarm, file_path)
        except (FileNotFoundError, IOError):
            return None

    @classmethod
    def from_json(cls, jsonobj):
        """
        Takes in a JSON-compatible dictionary and returns a new TestSkeleton object.
        """
        try:
            tests = jsonobj.pop("tests")
            return cls(
                descriptor=jsonobj["descriptor"],
                tests=[AssignmentTest.from_json_dict(test) for test in tests],
                disarm=jsonobj["disarm"],
                file_path=jsonobj["file_path"],
            )
        except KeyError as e:
            raise ValueError(
                "Incompatible dictionary constructor for TestSkeleton"
            ) from e

    def reload(self) -> bool:
        """
        Try to reload this test skeleton
        :return: True if the reload succeeded, false otherwise
        """
        new_skeleton = TestSkeleton.from_file(self.file_path)

        if new_skeleton is None:
            return False

        self.descriptor = new_skeleton.descriptor
        self.tests = new_skeleton.tests
        self.disarm = new_skeleton.disarm
        self.file_path = new_skeleton.file_path
        return True

    def run_tests(self, user: "User") -> Optional[Real]:
        total_score = 0.0

        try:
            os.chdir(
                os.path.join(os.environ["INSTALL_DIR"], ".temp", str(user.user_id))
            )
        except (WindowsError, OSError):
            print(
                'Could not access files for user "%i". Skipping' % user.user_id,
                file=user.log,
            )
            return None

        for count, test in enumerate(self.tests, 1):
            print("\n--Running test %i--" % count, file=user.log)

            if test.prompt_for_score:
                print("\nUser:", user.name)
            if test.run_and_match(user):
                if test.prompt_for_score:
                    print("Enter the score for this test:")
                    total_score += choose_float(
                        1000, allow_negative=True, allow_zero=True
                    )
                if test.point_val > 0:
                    print("--Adding %i points--" % test.point_val, file=user.log)
                elif test.point_val == 0:
                    print("--No points set for this test--", file=user.log)
                else:
                    print(
                        "--Subtracting %i points--" % abs(test.point_val), file=user.log
                    )
                total_score += test.point_val
            else:
                print("--Test failed--", file=user.log)
                if test.fail_comment:
                    user.comment += test.fail_comment + "\n"
                if test.test_must_pass:
                    break

            print("--Current score: %i--" % total_score, file=user.log)

        return total_score

    def to_json(self):
        """
        Return a new dictionary to represent the state of the skeleton in a
        JSON-compatible format.
        """
        attributes = attr.asdict(self)
        attributes["tests"] = [test.to_json() for test in self.tests]
        return attributes
