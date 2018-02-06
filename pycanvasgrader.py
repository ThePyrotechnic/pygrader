#!/usr/bin/env python3.6
"""
pycanvasgrader

Automates the grading of programming assignments on Canvas.
MUST create an 'access.token' file in the same directory as this file with
a valid Canvas OAuth2 token
REQUIRED File structure:
- pycanvasgrader
  -- skeletons
  -- temp
  access.token
  pycanvasgrader.py

  TODO implement skeleton creation wizard
  TODO test/implement visual grading

Usage:
    pycanvasgrader [options]

Options:
    --ua, --ungraded-assignments
    --us, --ungraded-submissions
    --skeleton=<skeleton>
"""
# built-ins
from enum import Enum
import json
import os
import pathlib
import re
import shutil
import subprocess
import sys
import importlib
from importlib import util
from typing import Callable, Dict, List, Sequence, Tuple, TypeVar

# 3rd-party
import attr
import requests
import toml
if importlib.util.find_spec('py'):
    import py

# globals
DISARM_ALL = False
DISARM_MESSAGER = False
DISARM_GRADER = False

RUN_WITH_TESTS = False
ONLY_RUN_TESTS = False
NUM_REGEX = re.compile(r'-?\d+\.\d+|-?\d+')
# r'[+-]?\d+\.\d+|\d+'
# r'[-+]?\d+(\.\d+)?'


# TODO determine whether or not should be capitalized
Enrollment = Enum('Enrollment', ['teacher', 'student', 'ta', 'observer', 'designer'])
T = TypeVar('T')


class PyCanvasGrader:
    """
    A PyCanvasGrader object; responsible for communicating with the Canvas API
    """

    def __init__(self):
        self.token = self.authenticate()
        if self.token == 'none':
            print('Unable to retrieve OAuth2 token')
            exit()

        self.session = requests.Session()
        self.session.headers.update({'Authorization': 'Bearer ' + self.token})

    @staticmethod
    def authenticate() -> str:
        """
        Responsible for retrieving the OAuth2 token for the session.
        :return: The OAuth2 token

        TODO Talk about "proper" OAuth2 authentication
        """
        try:
            with open('access.token', 'r', encoding='UTF-8') as access_file:
                for line in access_file:
                    token = line.strip()
                    if len(token) > 2:
                        return token
        except FileNotFoundError:
            print("Could not find an access.token file. You must place your Canvas OAuth token in a file named 'access.token', in this directory.")
            exit(1)

    def close(self):
        self.session.close()

    def courses(self, enrollment_type: Enrollment = None) -> list:
        """
        :param enrollment_type: (Optional) teacher, student, ta, observer, designer
        :return: A list of the user's courses as dictionaries, optionally filtered by enrollment_type
        """
        url = 'https://sit.instructure.com/api/v1/courses?per_page=100'
        if enrollment_type is not None:
            url += '&enrollment_type=' + enrollment_type.name.lower()

        response = self.session.get(url)
        return json.loads(response.text)

    def assignments(self, course_id: int, ungraded: bool = True) -> list:
        """
        :param course_id: Course ID to filter by
        :param ungraded: Whether to filter assignments by only those that have ungraded work. Default: True
        :return: A list of the course's assignments
        """
        url = 'https://sit.instructure.com/api/v1/courses/' + str(course_id) + '/assignments?per_page=100'
        if ungraded:
            url += '&bucket=ungraded'

        response = self.session.get(url)
        return json.loads(response.text)

    def submissions(self, course_id: int, assignment_id: int) -> list:
        """
        :param course_id: The ID of the course containing the assignment
        :param assignment_id: The ID of the assignment
        :return: A list of the assignment's submissions
        """
        url = 'https://sit.instructure.com/api/v1/courses/' + str(course_id) + '/assignments/' + str(assignment_id) + '/submissions?per_page=100'

        response = self.session.get(url)
        final_response = json.loads(response.text)
        while response.links.get('next'):
            response = self.session.get(response.links['next']['url'])
            final_response.extend(json.loads(response.text))

        return final_response

    def download_submission(self, submission: dict, filepath: str) -> bool:
        """
        Attempts to download the attachments for a given submission into the requested directory. Creates the directory if it does not exist.
        :param submission: The submission dictionary
        :param filepath: the path where the submission attachments will be placed
        :return: True if the request succeeded, False otherwise
        """
        try:
            user_id = submission['user_id']
            attachments = submission['attachments']
        except ValueError:
            return False

        for attachment in attachments:
            try:
                url = attachment['url']
                filename = attachment['filename']
            except ValueError:
                return False

            os.makedirs(os.path.join('temp', str(user_id)), exist_ok=True)
            r = self.session.get(url, stream=True)
            with open(os.path.join(filepath, filename), 'wb') as f:
                for chunk in r.iter_content(chunk_size=1024):
                    if chunk:
                        f.write(chunk)
        return True

    def user(self, course_id: int, user_id: int) -> dict:
        """
        :param course_id: The class to search
        :param user_id: The ID of the user
        :return: A dictionary with the user's information
        """
        url = 'https://sit.instructure.com/api/v1/courses/%i/users/%i' % (course_id, user_id)

        response = self.session.get(url)
        return json.loads(response.text)

    def grade_submission(self, course_id, assignment_id, user_id, grade):
        global DISARM_ALL, DISARM_GRADER
        url = 'https://sit.instructure.com/api/v1/courses/%i/assignments/%i/submissions/%i/?submission[posted_grade]=%i' \
              % (course_id, assignment_id, user_id, grade)

        if DISARM_ALL or DISARM_GRADER:
            print('Grader disarmed; grade will not actually be submitted')
            return 'dummy success'
        else:
            response = self.session.put(url)
            return json.loads(response.text)

    def message_user(self, recipient_id: int, body: str, subject: str = None):
        global DISARM_ALL, DISARM_MESSAGER
        url = 'https://sit.instructure.com/api/v1/conversations/'

        data = {
            'recipients[]': recipient_id,
            'body': body,
            'subject': subject
        }

        if DISARM_ALL or DISARM_MESSAGER:
            print('Messenger disarmed; user wil not actually be messaged')
            return 'dummy success'
        else:
            response = self.session.post(url, data)
            return json.loads(response.text)


def option(default=False):
    """
    Constructor for optional boolean configuartion attributes
    """
    return attr.ib(default=default, type=bool)


@attr.s
class AssignmentTest:
    """
    An abstract test to be run on an assignment submission
    TODO 'sequential' command requirement

    :param command: The command to be run.
    :param args: List of arguments to pass to the command. Use %s to denote a file name
    :param input_str: String to send to stdin
    :param target_file: The file to replace %s with
    :param output_match: An exact string that the output should match. If this and output_regex are None, then this Command always 'matches'
    :param output_regex: A regular expression that the string should match. Combines with output_match.
    If this and output_match are None, then this Command always 'matches'
    :param numeric_match: Enables numeric matching. This overrides string and regex matching
    :param timeout: Time, in seconds, that this Command should run for before timing out
    :param fail_notif: Message to be sent to user when test fails
    :param point_val: Amount of points that a successful match is worth (Can be negative)
    :param print_file: Whether to print the contents of the target_file being tested (Does nothing if no file is selected)
    :param single_file: Whether to assume the assignment is a single file and use the first file found as %s
    :param ask_for_target: Whether to prompt for a file in the current directory. Overrides file_target
    :param include_filetype: Whether to include the filetype in the %s substitution
    :param print_output: Whether to visibly print the output
    :param negate_match: Whether to negate the result of checking output_match and output_regex
    :param exact_match: Whether the naive string match (output_match) should be an exact check or a substring check
    """
    command = attr.ib(type=str)
    args = attr.ib(None, type=list)
    input_str = attr.ib(None, type=str)
    target_file = attr.ib(None, type=str)
    output_match = attr.ib(None, type=str)
    output_regex = attr.ib(None, converter=(
        lambda expr: re.compile(re.escape(expr)) if expr is not None else None))
    numeric_match = attr.ib(None, type=list)
    timeout = attr.ib(None, type=int)
    fail_notif = attr.ib(None, type=dict)
    point_val = attr.ib(0, type=int)

    print_file = option()
    single_file = option()
    ask_for_target = option()
    include_filetype = option(True)
    print_output = option(True)
    negate_match = option()
    exact_match = option()

    # The name of the test case
    name = attr.ib(None, type=str)

    @classmethod
    def from_json_dict(cls, json_dict: dict):
        if 'command' not in json_dict:
            return None

        json_dict['input_str'] = json_dict.pop('input', None)
        json_dict['fail_notif'] = json_dict.pop('fail_notification', None)

        return AssignmentTest(**json_dict)

    @classmethod
    def target_prompt(cls, command: str):
        path = pathlib.Path(os.getcwd())
        files = [file for file in path.iterdir() if file.is_file()]

        if not files:
            print('This directory is empty, unable to choose a file for the "%s" command' % command)
            return None

        return choose(
            files,
            'Select a file for the "%s" command:' % command
        ).name

    def run(self) -> dict:
        """
        Runs the Command
        :return: A dictionary containing the command's return code, stdout, and stderr
        """
        command = self.command
        args = self.args
        filename = self.target_file
        if filename is None:
            if self.single_file and len(os.listdir(os.getcwd())) > 0:
                filename = os.listdir(os.getcwd())[0]
            elif len(os.listdir(os.getcwd())) == 1:
                filename = os.listdir(os.getcwd())[0]
            elif self.ask_for_target:
                filename = AssignmentTest.target_prompt(self.command)

        if not self.include_filetype and filename is not None:
            filename = os.path.splitext(filename)[0]
        if filename is not None:
            if self.print_file:
                print('--FILE--')
                with open(filename, 'r') as f:
                    shutil.copyfileobj(f, sys.stdout)
                print('--END FILE--')
            command = self.command.replace('%s', filename)
            if args is not None:
                args = [arg.replace('%s', filename) for arg in args]

        try:
            if args:
                command_to_send = [command] + args
            else:
                command_to_send = command
            if sys.version_info[1] == 5:
                proc = subprocess.run(command_to_send, input=self.input_str, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, timeout=self.timeout, shell=True)

            else:
                proc = subprocess.run(command_to_send, input=self.input_str, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, timeout=self.timeout, encoding='UTF-8', shell=True)

        except subprocess.TimeoutExpired:
            return {'timeout': True}
        return {'returncode': proc.returncode, 'stdout': proc.stdout, 'stderr': proc.stderr}

    def run_and_match(self) -> bool:
        """
        Runs the command and matches the output to the output_match/regex. If neither are defined then this always returns true
        :return: Whether the output matched or not
        """
        global NUM_REGEX

        result = self.run()

        if result.get('timeout'):
            return False

        if self.print_output:
            print('\t--OUTPUT--')
            print(result['stdout'])
            print('\t--END OUTPUT--')
        if not any((self.output_match, self.output_regex, self.numeric_match)):
            return True

        if self.numeric_match is not None:
            numeric_match = self.numeric_match.copy()
            extracted_nums = map(float, re.findall(NUM_REGEX, result['stdout']))

            for number in extracted_nums:
                for num in numeric_match:
                    if isinstance(num, str):
                        numeric_match.remove(num)
                        range_vals = list(map(float, re.findall(NUM_REGEX, num)))
                        if len(range_vals) != 2:
                            continue
                        num = [range_vals[0] - range_vals[1], range_vals[0] + range_vals[1]]
                        numeric_match.append(num)
                    if isinstance(num, list):
                        if num[0] <= number <= num[1]:
                            numeric_match.remove(num)
                    elif isinstance(num, (int, float)):
                        if number == num:
                            numeric_match.remove(num)

            return len(numeric_match) == 0

        if self.output_regex:
            if self.output_regex.match(result['stdout']):
                print('--Matched regular expression--')
                if self.negate_match:
                    return False
                return True

        if self.output_match:
            if self.exact_match:
                condition = self.output_match == result['stdout']
            else:
                condition = self.output_match in result['stdout']

            if condition:
                print('--Matched string comparison--')
                if self.negate_match:
                    return False
                return True

        return self.negate_match


@attr.s
class TestSkeleton:
    """
    An abstract skeleton to handle testing of a specific group of files
    """

    descriptor = attr.ib(type=str)
    tests = attr.ib(type=List[AssignmentTest])  # Tests to run in the order that they are added.
    disarm = attr.ib(default=False, type=bool)  # Whether to actually submit grades/send messages

    @classmethod
    def from_file(cls, filename, dir='skeletons') -> 'TestSkeleton':
        with open(dir + '/' + filename) as skeleton_file:
            try:
                if filename.endswith('.json'):
                    data = json.load(skeleton_file)
                elif filename.endswith('.toml'):
                    data = toml.load(skeleton_file)
                else:
                    return None
            except (json.JSONDecodeError, toml.TomlDecodeError):
                print('There is an error in the', filename, 'skeleton file. This skeleton will not be available')
                return None
            try:
                descriptor = data['descriptor']
                tests = data['tests']
            except KeyError:
                return None
            else:
                disarm = data.get('disarm', False)
                defaults = data.get('default', {})
                test_list = []
                for name, json_dict in tests.items():
                    args = {**defaults, **json_dict, 'name': name}
                    test = AssignmentTest.from_json_dict(args)
                    if test is not None:
                        test_list.append(test)

                return TestSkeleton(descriptor, test_list, disarm)

    def run_tests(self, grader: PyCanvasGrader, user_id: int) -> Tuple[int, Dict]:
        global DISARM_ALL
        DISARM_ALL = self.disarm

        total_score = 0
        failures = {}

        for count, test in enumerate(self.tests, 1):
            print('\n--Running test %i--' % count)
            if test.run_and_match():
                if test.point_val > 0:
                    print('--Adding %i points--' % test.point_val)
                elif test.point_val == 0:
                    print('--No points set for this test--')
                else:
                    print('--Subtracting %i points--' % abs(test.point_val))
                total_score += test.point_val
            else:
                print('--Test failed--')
                failures[test.name] = -test.point_val
                if test.fail_notif:
                    try:
                        body = test.fail_notif['body']
                    except ValueError:
                        pass
                    else:
                        subject = test.fail_notif.get('subject')
                        grader.message_user(user_id, body, subject)

            print('--Current score: %i--' % total_score)
        return total_score, failures


def choose_val(hi_num: int, allow_zero: bool = False) -> int:
    for val in iter(input, None):
        if not val.isdigit():
            continue

        i = int(val)
        if i in range(0 if allow_zero else 1, hi_num):
            return i


def choose_bool() -> bool:
    for b in iter(input, None):
        if b.lower() in {'y', 'n', 'yes', 'no'}:
            return b.startswith(('y', 'Y'))


def parse_skeletons() -> list:
    """
    Responsible for validating and parsing the skeleton files in the "skeletons" directory
    :return: A list of valid skeletons
    """
    skeleton_list = []
    for skeleton_file in os.listdir('skeletons'):
        skeleton = TestSkeleton.from_file(skeleton_file)
        if skeleton is not None:
            skeleton_list.append(skeleton)
    return skeleton_list


def restart_program(grader: PyCanvasGrader):
    grader.close()
    init_tempdir()
    main()
    exit(0)


def init_tempdir():
    try:
        if os.path.exists('temp'):
            if os.path.exists('old-temp'):
                shutil.rmtree(os.path.join(os.path.dirname(os.path.abspath(__file__)), 'old-temp'))
            os.rename('temp', 'old-temp')
        os.makedirs('temp', exist_ok=True)
    except BaseException:
        print('An error occurred while initializing the "temp" directory.',
              'Please delete/create the directory manually and re-run the program')
        exit(1)


def choose(
        choices: Sequence[T],
        message: str = None,
        formatter: Callable[[T], str] = str) -> T:
    """
    Display the contents of a sequence and have the user enter a 1-based
    index for their selection.

    Takes an optional message to print before showing the choices
    """
    if message is not None:
        print(message)
    for i, choice in enumerate(choices, 1):
        print(i, formatter(choice), sep='.\t')

    i = -1
    while i not in range(1, len(choices) + 1):
        try:
            i = int(input())
        except (TypeError, ValueError):
            continue

    return choices[i - 1]


def main():
    if sys.version_info < (3, 5):
        print('Python 3.5+ is required')
        exit(1)

    init_tempdir()
    # Initialize grading session and fetch courses
    grader = PyCanvasGrader()

    selected_role = getattr(Enrollment, choose(
        ['teacher', 'ta'],
        'Choose a class role to filter by:'
    ))

    course_list = grader.courses(selected_role)
    if len(course_list) < 1:
        input('No courses were found. Press enter to restart')
        restart_program(grader)

    # Have user select course
    course_id = choose(
        course_list,
        'Choose a course from the following list:',
        formatter=lambda course: '%s (%s)' % (course.get('name'), course.get('course_code'))
    ).get('id')
    print('Show only ungraded assignments? (y or n):')
    ungraded = choose_bool()
    assignment_list = grader.assignments(course_id, ungraded=ungraded)

    if len(assignment_list) < 1:
        input('No assignments were found. Press enter to restart')
        restart_program(grader)

    # Have user choose assignment
    assignment_id = choose(
        assignment_list,
        'Choose an assignment to grade:',
        formatter=lambda assignment: assignment.get('name')
    ).get('id')

    # Get list of submissions for this assignment
    submission_list = grader.submissions(course_id, assignment_id)
    if len(submission_list) < 1:
        input('There are no submissions for this assignment. Press enter to restart')
        restart_program(grader)

    print('Only grade currently ungraded submissions? (y or n):')
    ungraded_only = choose_bool()
    # Match the user IDs found in the zip with the IDs in the online submission
    user_submission_dict = {}
    for submission in submission_list:
        # Skip assignments that have been graded already
        if ungraded_only and submission.get('grader_id') is not None:
            continue
        user_id = submission.get('user_id')
        if submission.get('attachments') is not None:
            if grader.download_submission(submission, os.path.join('temp', str(user_id))):
                user_submission_dict[user_id] = submission['id']
            else:
                print("There was a problem downloading this user's submission. Skipping.")

    if len(user_submission_dict) < 1:
        input('Could not download any submissions. Press enter to restart')
        restart_program(grader)

    s = 's' if user_submission_dict else ''
    print('Successfully retrieved %i submission%s. Is this correct? (y or n):' % (len(user_submission_dict), s))
    correct = choose_bool()
    if not correct:
        restart_program(grader)

    skeleton_list = parse_skeletons()
    if len(skeleton_list) < 1:
        print('Could not find any skeleton files in the skeletons directory.',
              'Would you like to create one now? (y or n):')
        if choose_bool():
            # TODO implement the skeleton wizard
            print(NotImplemented)
        else:
            pass
        exit(0)

    selected_skeleton = choose(
        skeleton_list,
        'Choose a skeleton to use for grading this assignment:',
        formatter=lambda skel: skel.descriptor
    )

    name_dict = {}
    print('Students to grade: [Name (email)]\n----')
    for user_id in user_submission_dict:
        user_data = grader.user(course_id, user_id)
        if user_data.get('name') is not None:
            name_dict[user_id] = user_data['name']
        name = user_data.get('name')
        email = user_data.get('email')
        print(name, '(%s)' % email, sep='\t')
    print('----\n')

    print('Require confirmation before submitting grades? (y or n)')
    grade_conf = choose_bool()

    # type: Dict[name, List[test_case]]
    failures = {}

    input('Press enter to begin grading\n')
    for cur_user_id in user_submission_dict:
        try:
            os.chdir(os.path.join('temp', str(cur_user_id)))
        except (WindowsError, OSError):
            print('Could not access files for user "%i". Skipping' % cur_user_id)
            continue
        print('--Grading user "%s"--' % name_dict.get(cur_user_id))
        score, issues = selected_skeleton.run_tests(grader, cur_user_id)

        if score < 0:
            score = 0

        action_list = [
            'Submit this grade', 'Modify this grade',
            'Skip this submission', 'Re-grade this submission'
        ]

        while True:
            print('\n--All tests completed--\nGrade for this assignment:', score)
            if not grade_conf:
                grader.grade_submission(course_id, assignment_id, cur_user_id, score)
                print('Grade submitted')
                break
            else:
                selected_action = choose(action_list, 'Choose an action:')

                if selected_action == 'Submit this grade':
                    grader.grade_submission(course_id, assignment_id, cur_user_id, score)
                    print('Grade submitted')
                    break
                elif selected_action == 'Modify this grade':
                    print('Enter a new grade for this submission:')
                    score = choose_val(1000, allow_zero=True)
                elif selected_action == 'Skip this submission':
                    break
                elif selected_action == 'Re-grade this submission':
                    score, issues = selected_skeleton.run_tests(grader, cur_user_id)
        if len(issues) > 0:
            name = name_dict.get(cur_user_id, str(cur_user_id))
            failures[name] = issues
        try:
            os.chdir(os.path.join('..', '..'))
        except (WindowsError, OSError):
            print('Unable to leave current directory')
            exit(1)

    if len(failures) > 1:
        with open('failures.json', 'w') as failures_file:
            json.dump(failures, failures_file)

    print('Finished grading all submissions for this assignment')


if __name__ == '__main__':
    if RUN_WITH_TESTS or ONLY_RUN_TESTS:
        py.test.cmdline.main()
    if not ONLY_RUN_TESTS:
        main()
