#!/usr/bin/env python3.6
"""
pycanvasgrader

Automates the grading of programming assignments on Canvas.
MUST create an 'access.token' file in the same directory as this file with
a valid Canvas OAuth2 token
REQUIRED File structure:
- pycanvasgrader
  -- skeletons
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
from importlib import util
from datetime import datetime
from numbers import Real
from typing import Callable, Dict, List, Sequence, Tuple, TypeVar

# 3rd-party
import attr
import requests
import toml

if util.find_spec('py'):
    import py

# globals
DISARM_ALL = False
DISARM_MESSAGER = False
DISARM_GRADER = False

RUN_WITH_TESTS = False
ONLY_RUN_TESTS = False
NUM_REGEX = re.compile(r'-?\d+\.\d+|-?\d+')
INSTALL_DIR = '.'
CURRENTLY_SAVED = False

# TODO determine whether or not should be capitalized
Enrollment = Enum('Enrollment', ['teacher', 'student', 'ta', 'observer', 'designer'])
T = TypeVar('T')


class PyCanvasGrader:
    """
    A PyCanvasGrader object; responsible for communicating with the Canvas API
    """

    def __init__(self, course_id: int = -1, assignment_id: int = -1):
        self.token = self.authenticate()

        self.session = requests.Session()
        self.session.headers.update({'Authorization': 'Bearer ' + self.token})

        self.course_id = course_id
        self.assignment_id = assignment_id

    def __repr__(self):
        return 'PyCanvasGrader(course_id={}, assignment_id={})'.format(self.course_id, self.assignment_id)

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
            print("Could not find an access.token file. You must place your Canvas OAuth token in a file named\
             'access.token', in this directory.")
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

    def assignments(self, ungraded: bool = True) -> list:
        """
        :param ungraded: Whether to filter assignments by only those that have ungraded work. Default: True
        :return: A list of the course's assignments
        """
        url = 'https://sit.instructure.com/api/v1/courses/' + str(self.course_id) + '/assignments?per_page=100'
        if ungraded:
            url += '&bucket=ungraded'

        response = self.session.get(url)
        return json.loads(response.text)

    def submissions(self) -> list:
        """
        :return: A list of the assignment's submissions
        """
        url = 'https://sit.instructure.com/api/v1/courses/' + str(self.course_id) + '/assignments/' + str(
            self.assignment_id) + '/submissions?per_page=100'

        response = self.session.get(url)
        final_response = json.loads(response.text)
        while response.links.get('next'):
            response = self.session.get(response.links['next']['url'])
            final_response.extend(json.loads(response.text))

        return final_response

    def submission(self, user_id: int) -> dict:
        """
        Get information about a single submission
        :param user_id: The user ID of the user whose submission is to be requested
        :return: A dictionary which represents the submission object
        """
        url = 'https://sit.instructure.com/api/v1/courses/{}/assignments/{}/submissions/{}'.format(
            self.course_id, self.assignment_id, user_id
        )

        response = self.session.get(url)
        return json.loads(response.text)

    def download_submission(self, submission: dict) -> bool:
        """
        Attempts to download the attachments for a given submission.
        :param submission: The submission dictionary
        :return: True if the request succeeded, False otherwise
        """
        global INSTALL_DIR

        try:
            user_id = submission['user_id']
            attachments = submission['attachments']
        except ValueError:
            return False

        # First download everything to .new,
        # then clear .temp/user_id,
        # then move from .new to .temp/user_id.
        # This ensures that the download is complete before overwriting.
        try:
            os.chdir(INSTALL_DIR)
            os.makedirs(os.path.join('.temp', str(user_id), '.new'), exist_ok=True)
            os.chdir(os.path.join('.temp', str(user_id), '.new'))

            for attachment in attachments:
                try:
                    url = attachment['url']
                    filename = attachment['filename']
                except ValueError:
                    return False

                r = self.session.get(url, stream=True)
                with open(filename, 'wb') as f:
                    for chunk in r.iter_content(chunk_size=1024):
                        if chunk:
                            f.write(chunk)

            os.chdir('..')
            for cur_file in os.listdir('.'):
                if os.path.isfile(cur_file):
                    os.remove(cur_file)

            os.chdir('.new')
            for cur_file in os.listdir('.'):
                shutil.move(cur_file, '..')
            os.chdir('..')
            os.rmdir('.new')
        except:
            print('Unable work with files in the installation directory')
            print('The program will likely not work as intended.')
            print('Please close the program, ensure that it has permission to read and write in the current directory, and retry.')
            return False
        return True

    def user(self, user_id: int) -> dict:
        """
        :param user_id: The ID of the user
        :return: A dictionary with the user's information
        """
        url = 'https://sit.instructure.com/api/v1/courses/%i/users/%i' % (self.course_id, user_id)

        response = self.session.get(url)
        return json.loads(response.text)

    def grade_submission(self, user_id: int, grade: Real):
        global DISARM_ALL, DISARM_GRADER
        if grade is None:
            grade = 'NaN'
        url = 'https://sit.instructure.com/api/v1/courses/%i/assignments/%i/submissions/%i/?submission[posted_grade]=%s' \
              % (self.course_id, self.assignment_id, user_id, str(grade))

        if DISARM_ALL or DISARM_GRADER:
            print('Grader disarmed; grade will not actually be submitted')
            return 'dummy success'
        else:
            response = self.session.put(url)
            return json.loads(response.text)

    def comment_on_submission(self, user_id: int, comment: str):
        global DISARM_ALL, DISARM_MESSAGER
        url = 'https://sit.instructure.com/api/v1/courses/%i/assignments/%i/submissions/%i/?comment[text_comment]=%s' \
              % (self.course_id, self.assignment_id, user_id, comment)

        if DISARM_ALL or DISARM_MESSAGER:
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

    @property
    def cache_file(self):
        """
        Cache file to use for the current course/assignment combination
        """
        file = os.path.join(
            INSTALL_DIR,
            '.cache',
            str(self.course_id),
            str(self.assignment_id)
        )
        return os.path.abspath(file)


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
    command = attr.ib(type=str)
    args = attr.ib(None, type=list)
    input_str = attr.ib(None, type=str)
    target_file = attr.ib(None, type=str)
    output_match = attr.ib(None, type=str)
    output_regex = attr.ib(None, converter=(
        lambda expr: re.compile(re.escape(expr)) if expr is not None else None))
    numeric_match = attr.ib(None, type=list)
    timeout = attr.ib(None, type=int)
    fail_comment = attr.ib(None, type=str)
    point_val = attr.ib(0, type=float)

    test_must_pass = option(False)
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
        json_dict['fail_comment'] = json_dict.pop('fail_comment', None)

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

    def run(self, user: 'User') -> dict:
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
                user.log += '--FILE--\n'
                with open(filename, 'r') as f:
                    file_as_str = f.read()
                    user.log += file_as_str
                user.log += '--END FILE--\n'
            command = self.command.replace('%s', filename)
            if args is not None:
                args = [arg.replace('%s', filename) for arg in args]

        try:
            if args:
                command_to_send = [command] + args
            else:
                command_to_send = command
            if sys.version_info[1] == 5:
                proc = subprocess.run(command_to_send, input=self.input_str, stdout=subprocess.PIPE,
                                      stderr=subprocess.STDOUT, timeout=self.timeout, shell=True)

            else:
                proc = subprocess.run(command_to_send, input=self.input_str, stdout=subprocess.PIPE,
                                      stderr=subprocess.STDOUT, timeout=self.timeout, encoding='UTF-8', shell=True)

        except subprocess.TimeoutExpired:
            return {'timeout': True}
        return {'returncode': proc.returncode, 'stdout': proc.stdout, 'stderr': proc.stderr}

    def run_and_match(self, user: 'User') -> bool:
        """
        Runs the command and matches the output to the output_match/regex. If neither are defined then this always returns true
        :return: Whether the output matched or not
        """
        global NUM_REGEX

        result = self.run(user)

        if result.get('timeout'):
            return False

        if self.print_output:
            user.log += '\t--OUTPUT--\n'
            user.log += result['stdout']
            user.log += '\n\t--END OUTPUT--\n'
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
                user.log += '--Matched regular expression--\n'
                if self.negate_match:
                    return False
                return True

        if self.output_match:
            if self.exact_match:
                condition = self.output_match == result['stdout']
            else:
                condition = self.output_match in result['stdout']

            if condition:
                user.log += '--Matched string comparison--\n'
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
    file_path = attr.ib(default='', type=str)

    @classmethod
    def from_file(cls, filename, skeleton_dir='skeletons') -> 'TestSkeleton':
        global INSTALL_DIR
        os.chdir(INSTALL_DIR)

        try:
            with open(os.path.join(skeleton_dir, filename)) as skeleton_file:
                try:
                    if filename.endswith('.json'):
                        data = json.load(skeleton_file)
                    elif filename.endswith('.toml'):
                        data = toml.load(skeleton_file)
                    else:
                        return None
                except (json.JSONDecodeError, toml.TomlDecodeError) as e:
                    print('There is an error in the', filename, 'skeleton file. This skeleton will not be available')
                    print('Error:', e)
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

                    return TestSkeleton(descriptor, test_list, disarm, os.path.join(skeleton_dir, filename))
        except (FileNotFoundError, IOError):
            return None

    def reload(self) -> bool:
        """
        Try to reload this test skeleton
        :return: True if the reload succeeded, false otherwise
        """
        new_skeleton = TestSkeleton.from_file(self.file_path, '')
        if new_skeleton is not None:
            self.descriptor = new_skeleton.descriptor
            self.tests = new_skeleton.tests
            self.disarm = new_skeleton.disarm
            self.file_path = new_skeleton.file_path
            return True
        else:
            return False

    def run_tests(self, user: 'User') -> Tuple[int, Dict]:
        global DISARM_ALL, INSTALL_DIR
        DISARM_ALL = self.disarm

        user_id = user.user_id

        total_score = 0

        user.log = ''

        try:
            os.chdir(os.path.join(INSTALL_DIR, '.temp', str(user_id)))
        except (WindowsError, OSError):
            user.log += 'Could not access files for user "%i". Skipping\n' % user_id
            return None

        for count, test in enumerate(self.tests, 1):
            user.log += '\n--Running test %i--\n' % count
            if test.run_and_match(user):
                if test.point_val > 0:
                    user.log += '--Adding %i points--\n' % test.point_val
                elif test.point_val == 0:
                    user.log += '--No points set for this test--\n'
                else:
                    user.log += '--Subtracting %i points--\n' % abs(test.point_val)
                total_score += test.point_val
            else:
                user.log += '--Test failed--\n'
                if test.fail_comment:
                    user.comment += test.fail_comment + '\n'
                if test.test_must_pass:
                    break

            user.log += '--Current score: %i--\n' % total_score
        return total_score


@attr.s
class User:
    user_id = attr.ib(type=int)
    submission_id = attr.ib(type=int)
    name = attr.ib(type=str)
    email = attr.ib(type=str)
    last_posted_grade = attr.ib(type=Real)
    grade_matches_submission = attr.ib(type=bool)
    attempt = attr.ib(type=int)
    grade = attr.ib(type=Real, default=None)
    comment = attr.ib(type=str, default='')
    log = attr.ib(type=str, default='')

    def __attrs_post_init__(self):
        if self.grade is None:
            self.grade = self.last_posted_grade

    def __str__(self):
        grade = 'ungraded' if self.grade is None else self.grade
        submit_status = 'posted' if self.submitted else 'not posted'
        if not self.grade_matches_submission:
            submit_status += ' - needs re-grading (new submission)'
        email = self.email or 'No email'
        return '{} ({}): {} [{}]'.format(self.name, email, grade, submit_status)

    @property
    def submitted(self):
        return self.grade == self.last_posted_grade

    def grade_self(self, test_skeleton: TestSkeleton):
        grade = test_skeleton.run_tests(self)
        if grade is None:
            return
        else:
            if grade != self.grade:
                self.grade = grade

    def submit_grade(self, grader: PyCanvasGrader):
        grader.grade_submission(self.user_id, self.grade)
        grader.comment_on_submission(self.user_id, self.comment)
        self.last_posted_grade = self.grade

    def update(self, grader: PyCanvasGrader) -> bool:

        new_submission = grader.submission(self.user_id)
        if new_submission['attempt'] > self.attempt:
            if grader.download_submission(new_submission):
                # noinspection PyArgumentList
                self.__init__(user_id=self.user_id,
                              submission_id=new_submission['id'],
                              name=self.name,
                              email=self.email,
                              last_posted_grade=new_submission['score'],
                              grade_matches_submission=new_submission['grade_matches_current_submission'],
                              attempt=new_submission['attempt'])
                return True
        return False


def parse_skeleton(skeleton_file: str) -> TestSkeleton:
    """
    Parse a single TestSkeleton
    :return: The parsed skeleton, or None if parsing failed
    """
    return TestSkeleton.from_file(skeleton_file)


def parse_skeletons() -> list:
    """
    Responsible for validating and parsing the skeleton files in the "skeletons" directory
    :return: A list of valid skeletons
    """
    global INSTALL_DIR

    os.chdir(INSTALL_DIR)
    skeleton_list = []
    for skeleton_file in os.listdir('skeletons'):
        skeleton = parse_skeleton(skeleton_file)
        if skeleton is not None:
            skeleton_list.append(skeleton)
    return skeleton_list


def close_program(grader: PyCanvasGrader, restart=False):
    grader.close()
    if restart:
        init_tempdir()
        main()
    exit(0)


def init_tempdir():
    global INSTALL_DIR

    try:
        os.chdir(INSTALL_DIR)
        if os.path.exists('.temp'):
                shutil.rmtree('.temp')
        os.makedirs('.temp', exist_ok=True)
    except:
        print('An error occurred while initializing the "temp" directory.',
              'Please delete/create the directory manually and re-run the program')
        exit(1)


def open_file(filename: str, mode: str = 'r'):
    try:
        file = open(filename, mode=mode)
    except (FileNotFoundError, IOError):
        return None
    else:
        return file


def load_prefs() -> dict:
    prefs_file = open_file('preferences.toml')
    pref_vals = {}
    if prefs_file is not None:
        try:
            pref_vals = toml.load(prefs_file)
        except toml.TomlDecodeError:
            print('Preferences file is invalid. Is it valid TOML?')

    # To simplify logic in the main functions, prefs['known_category'] is always defined
    prefs = {
        'session': pref_vals.get('session', {}),
        'quickstart': pref_vals.get('quickstart', {})
    }

    return prefs


def save_prefs(prefs: dict, new_prefs: dict):
    prefs = {**prefs, **new_prefs}
    try:
        with open('preferences.toml', mode='w') as prefs_file:
            toml.dump(prefs, prefs_file)
    except IOError:
        print('Unable to write preferences.toml')

        
def month_year(time_string: str) -> str:
    dt = datetime.strptime(time_string, '%Y-%m-%dT%H:%M:%SZ')
    return dt.strftime('%b %Y')


def choose_course(course_list) -> int:
    return choose(
        course_list,
        'Choose a course from the following list:',
        formatter=lambda c: '%s (%s)' % (c.get('name'), month_year(c['start_at']))
    ).get('id')


def choose_assignment(assignment_list) -> int:
    return choose(
        assignment_list,
        'Choose an assignment to grade:',
        formatter=lambda assignment: assignment.get('name')
    ).get('id')


def choose_val(hi_num: int, allow_negative: bool = False, allow_zero: bool = False, allow_float: bool = False) -> int:
    """
    Ask the user for a number and return the result if it is valid
    :param hi_num: The maximum number to allow
    :param allow_negative: Whether to allow negative numbers
    :param allow_zero: Whether to allow zero
    :param allow_float: Whether to allow floating point values
    :return: The user's numeric input
    """
    for val in iter(input, None):
        try:
            float(val)
        except ValueError:
            continue

        if allow_float:
            i = float(val)
        else:
            i = int(val)
        if allow_negative:
            if not allow_zero and i == 0:
                continue
            elif i <= hi_num:
                return i
            continue

        if i in range(0 if allow_zero else 1, hi_num + 1):
            return i


def choose_bool() -> bool:
    for b in iter(input, None):
        if b.lower() in {'y', 'n', 'yes', 'no'}:
            return b.startswith(('y', 'Y'))


def get_lines():
    while True:
        # Get every line until the first empty line
        yield from iter(input, '')

        # Get the next line and check if it is empty. If not, continue
        nextline = input()
        if nextline == '':
            break
        else:
            yield nextline


def multiline_input() -> str:
    return '\n'.join(get_lines()).rstrip()


def list_choices(
        choices: Sequence[T],
        message: str = None,
        formatter: Callable[[T], str] = str,
        msg_below: bool = False,
        start_at: int = 1):

    if not msg_below and message is not None:
        print(message)

    for i, choice in enumerate(choices, start_at):
        print(i, formatter(choice), sep='.\t')

    if msg_below and message is not None:
        print(message)


def choose(
        choices: Sequence[T],
        message: str = None,
        formatter: Callable[[T], str] = str,
        msg_below: bool = False) -> T:
    """
    Display the contents of a sequence and have the user enter a 1-based
    index for their selection.

    Takes an optional message to print before showing the choices
    """
    list_choices(choices, message, formatter, msg_below)

    i = choose_val(len(choices), False)
    return choices[i - 1]


def print_on_curline(msg: str):
    sys.stdout.write('\r')
    sys.stdout.flush()
    sys.stdout.write(msg)
    sys.stdout.flush()


def save_state(grader: PyCanvasGrader, test_skeleton: TestSkeleton, users: List[User]):
    global INSTALL_DIR, CURRENTLY_SAVED
    print_on_curline('Saving state...')
    try:
        os.chdir(INSTALL_DIR)
        cache_dir = os.path.join('.cache', str(grader.course_id), str(grader.assignment_id))
        os.makedirs(cache_dir, exist_ok=True)
        os.chdir(cache_dir)

        if os.path.exists('.temp'):
            shutil.rmtree('.temp')
        shutil.copytree(os.path.join(INSTALL_DIR, '.temp'), '.temp')

        with open('.cachefile', mode='w') as cache_file:
            print(test_skeleton, file=cache_file)
            print(users, file=cache_file)

        print_on_curline('State saved.    \n')
        CURRENTLY_SAVED = True
        os.chdir(INSTALL_DIR)
    except:
        print('There was an error while saving the state.')
        print('Make sure the program has permission to read/write in {}'.format(os.path.join(INSTALL_DIR, '.cache')))
        print('and that the directory is not in use.')
        os.chdir(INSTALL_DIR)


def load_state(course_id: int, assignment_id: int):
    global INSTALL_DIR

    os.chdir(INSTALL_DIR)
    if os.path.exists('.temp'):
        shutil.rmtree('.temp')

    os.chdir(os.path.join('.cache', str(course_id), str(assignment_id)))
    shutil.copytree('.temp', os.path.join(INSTALL_DIR, '.temp'))
    with open('.cachefile') as cache_file:
        test_skeleton = eval(cache_file.readline())
        users = eval(cache_file.readline())

        os.chdir(INSTALL_DIR)
        return test_skeleton, users


def grade_all_submissions(test_skeleton: TestSkeleton, users: List[User], only_ungraded: bool = False) -> bool:
    if only_ungraded:
        users = [u for u in users if u.grade is None]
        if len(users) == 0:
            print('No currently ungraded submissions to grade.')
            return False
    
    total = len(users)

    for count, user in enumerate(users):
        print_on_curline('grading ({}/{})'.format(count, total))
        user.grade_self(test_skeleton)
    print_on_curline('grading complete ({0}/{0})\n'.format(total))
    return True


def submit_all_grades(grader: PyCanvasGrader, users: list) -> bool:
    modified = False
    for user in users:
        if not user.submitted:
            user.submit_grade(grader)
            modified = True
    return modified


def user_menu(grader: PyCanvasGrader, test_skeleton: TestSkeleton, user: User):
    global CURRENTLY_SAVED

    # This way strings only need to be updated once
    possible_opts = {
        'log': 'View test log',
        'rerun': 'Re-run tests',
        'run': 'Run tests',
        'submit': 'Submit this grade',
        'modify': 'Modify this user\'s grade',
        'comment': 'Edit the comment for this grade',
        'update': 'Update this user\'s submission',
        'clear': 'Clear this user\'s grade',
        'back': 'Return to the main menu'
    }

    while True:
        options = []
        if user.log != '':
            options.append(possible_opts['rerun'])
            options.append(possible_opts['log'])
        else:
            options.append(possible_opts['run'])
        if not user.submitted or not user.grade_matches_submission:
            options.append(possible_opts['submit'])
        options.append(possible_opts['modify'])
        options.append(possible_opts['comment'])
        options.append(possible_opts['update'])
        if user.grade is not None:
            options.append(possible_opts['clear'])
        options.append(possible_opts['back'])

        print('User Menu |', user)
        if not user.submitted:
            last_grade = 'ungraded' if user.last_posted_grade is None else user.last_posted_grade
            print('Latest posted grade:', last_grade)
        print('-')
        choice = choose(options)

        if choice == possible_opts['log']:
            os.system('cls' if os.name == 'nt' else 'clear')
            print(user.log)
        elif choice in (possible_opts['rerun'], possible_opts['run']):
            os.system('cls' if os.name == 'nt' else 'clear')
            grade_before = user.grade
            user.grade_self(test_skeleton)
            if user.grade != grade_before:
                CURRENTLY_SAVED = False
        elif choice == possible_opts['submit']:
            os.system('cls' if os.name == 'nt' else 'clear')
            submitted_before = user.submitted
            user.submit_grade(grader)
            if not user.grade_matches_submission:
                user.grade_matches_submission = True
                CURRENTLY_SAVED = False
            if user.submitted != submitted_before:
                CURRENTLY_SAVED = False
        elif choice == possible_opts['modify']:
            grade_before = user.grade
            print('Enter a new grade: ')
            user.grade = choose_val(1000, allow_negative=True, allow_zero=True, allow_float=True)
            if user.grade != grade_before:
                CURRENTLY_SAVED = False
            os.system('cls' if os.name == 'nt' else 'clear')
        elif choice == possible_opts['comment']:
            cur_comment = user.comment
            if cur_comment == '':
                print('This user has no current comment.')
            else:
                print('Current comment:')
                print(user.comment)
            print('Type the new comment below, and press enter twice when you are finished.')
            inp = multiline_input()
            if inp != '':
                user.comment = inp
                if user.comment != cur_comment:
                    CURRENTLY_SAVED = False
            os.system('cls' if os.name == 'nt' else 'clear')
        elif choice == possible_opts['update']:
            os.system('cls' if os.name == 'nt' else 'clear')
            if user.update(grader):
                CURRENTLY_SAVED = False
                print('A new submission has been downloaded for this user.')
            else:
                print('No available updates for this user.')
        elif choice == possible_opts['clear']:
            os.system('cls' if os.name == 'nt' else 'clear')
            grade_before = user.grade
            user.grade = None
            if user.grade != grade_before:
                CURRENTLY_SAVED = False
        elif choice == possible_opts['back']:
            os.system('cls' if os.name == 'nt' else 'clear')
            return


def main_menu(grader: PyCanvasGrader, test_skeleton: TestSkeleton, users: list, prefs: dict):
    global CURRENTLY_SAVED

    print('Main Menu\n-')
    list_choices(users)
    print('-')

    options = {
        'grade_all': 'Grade all submissions',
        'grade_ungraded': 'Grade only ungraded submissions',
        'submit_all': 'Submit all grades',
        'reload_skeleton': 'Reload test skeleton',
        'save': 'Save changes',
        'save_and_quit': 'Save and quit',
        'quit': 'Quit'
    }

    # Doing it this way preserves order while still only needing to update 1 string if needed
    opt_list = [
        options['grade_all'],
        options['grade_ungraded'],
        options['submit_all'],
        options['reload_skeleton'],
    ]
    if not CURRENTLY_SAVED:
        opt_list.append(options['save'])
        opt_list.append(options['save_and_quit'])

    opt_list.append(options['quit'])

    list_choices(opt_list,
                 ('Choose a user to work with that user individually,\n'
                  'or enter an action from the menu above.'),
                 msg_below=True,
                 start_at=len(users) + 1)

    choice = choose_val(len(opt_list) + len(users))

    if choice <= len(users):
        os.system('cls' if os.name == 'nt' else 'clear')
        user_menu(grader, test_skeleton, users[choice - 1])
    else:
        selection = opt_list[choice - len(users) - 1]
        if selection == options['grade_all']:
            os.system('cls' if os.name == 'nt' else 'clear')
            success = grade_all_submissions(test_skeleton, users)
            if success and not CURRENTLY_SAVED and not prefs['session'].get('disable_autosave'):
                save_state(grader, test_skeleton, users)
            elif success:
                CURRENTLY_SAVED = False
        elif selection == options['grade_ungraded']:
            os.system('cls' if os.name == 'nt' else 'clear')
            success = grade_all_submissions(test_skeleton, users, only_ungraded=True)
            if success and not CURRENTLY_SAVED and not prefs['session'].get('disable_autosave'):
                save_state(grader, test_skeleton, users)
            elif success:
                CURRENTLY_SAVED = False
        elif selection == options['submit_all']:
            os.system('cls' if os.name == 'nt' else 'clear')
            modified = submit_all_grades(grader, users)
            if modified:
                CURRENTLY_SAVED = False
        elif selection == options['reload_skeleton']:
            os.system('cls' if os.name == 'nt' else 'clear')
            if not test_skeleton.reload():
                print('There was an error reloading this skeleton. It has not been reloaded.')
                print('Double-check the file\'s syntax, and make sure there are no typos.')
            else:
                print('Successfully reloaded the test skeleton.')
                CURRENTLY_SAVED = False
        elif selection == options['save']:
            os.system('cls' if os.name == 'nt' else 'clear')
            if not CURRENTLY_SAVED:
                save_state(grader, test_skeleton, users)
            else:
                print('Nothing to save.')
        elif selection == options['save_and_quit']:
            if not CURRENTLY_SAVED:
                save_state(grader, test_skeleton, users)
            close_program(grader)
        elif selection == options['quit']:
            if not CURRENTLY_SAVED:
                print('You have unsaved changes in the current grading session.')
                print('Would you like to save them before quitting? (y or n)')
                if choose_bool():
                    save_state(grader, test_skeleton, users)
            
            close_program(grader)


def startup(grader: PyCanvasGrader, prefs: dict) -> (int, int):
    session = prefs['session']
    quickstart = prefs['quickstart']

    role_str = quickstart.get('role')
    if type(role_str) == str:
        role_str = role_str.lower()
    try:
        selected_role = Enrollment[role_str]
    except KeyError:
        selected_role = Enrollment[choose(
            ['teacher', 'ta'],
            'Choose a class role to filter by:'
        )]

    course_list = grader.courses(selected_role)
    if len(course_list) < 1:
        input('No courses were found for the selected role. Press enter to restart')
        close_program(grader, restart=True)

    course_id = quickstart.get('course_id')
    if not course_id or not isinstance(course_id, int):
        course_id = choose_course(course_list)
    else:
        # must validate course_id from preferences file
        valid = any(c.get('id') == course_id for c in course_list)
        if not valid:
            course_id = choose_course(course_list)

    grader.course_id = course_id

    if not session.get('no_save_prompt') and \
            (not quickstart.get('course_id') or not quickstart.get('role')):
        print('Save these settings for faster startup next time? (y or n):')
        if choose_bool():
            save_prefs(prefs, {'quickstart': {'role': selected_role.name, 'course_id': course_id}})

    assignment_list = grader.assignments(ungraded=False)
    if len(assignment_list) < 1:
        input('No assignments were found. Press enter to restart')
        close_program(grader, restart=True)

    assignment_id = quickstart.get('assignment_id')
    if not assignment_id or not type(assignment_id) == int:
        assignment_id = choose_assignment(assignment_list)
    else:
        # must validate assignment_id from preferences file
        valid = True in (a.get('id') == assignment_id for a in assignment_list)
        if not valid:
            assignment_id = choose_assignment(assignment_list)

    grader.assignment_id = assignment_id

    return course_id, assignment_id


def grade_assignment(grader: PyCanvasGrader, prefs: dict):
    session = prefs['session']
    quickstart = prefs['quickstart']

    # Get list of submissions for this assignment
    submission_list = grader.submissions()
    if len(submission_list) < 1:
        input('There are no submissions for this assignment. Press enter to restart')
        close_program(grader, restart=True)

    ungraded_only = session.get('only_download_ungraded')
    if ungraded_only is None:
        print('Only download currently ungraded submissions? (y or n):')
        ungraded_only = choose_bool()

    # Create users from submissions
    users = []
    total = len(submission_list)
    failed = 0

    os.system('cls' if os.name == 'nt' else 'clear')
    for count, submission in enumerate(submission_list):
        if ungraded_only and submission['grade_matches_current_submission'] and submission['score'] is not None:
            continue
        user_id = submission.get('user_id')
        if submission.get('attachments') is not None:
            print_on_curline('downloading submissions... ({}/{})'.format(count, total))
            if grader.download_submission(submission):
                user_data = grader.user(user_id)
                users.append(User(user_id, submission['id'], user_data['name'], user_data.get('email'),
                                  submission['score'], submission['grade_matches_current_submission'], submission['attempt']))
            else:
                failed += 1
    print_on_curline('Submissions downloaded. ({} total, {} failed to validate)\n\n'.format(total, failed))

    if len(users) == 0:
        print('No submissions yet for this assignment.')

    selected_skeleton = None
    if quickstart.get('skeleton'):
        selected_skeleton = parse_skeleton(quickstart.get('skeleton'))

    if selected_skeleton is None:
        skeleton_list = parse_skeletons()
        selected_skeleton = choose(
            skeleton_list,
            'Choose a skeleton to use for grading this assignment:',
            formatter=lambda skel: skel.descriptor
        )
    if not session.get('disable_autosave'):
        save_state(grader, selected_skeleton, users)

    # Display main menu
    while True:
        main_menu(grader, selected_skeleton, users, prefs)


def main():
    global INSTALL_DIR, CURRENTLY_SAVED

    if sys.version_info < (3, 5):
        print('Python 3.5+ is required')
        exit(1)

    os.system('cls' if os.name == 'nt' else 'clear')

    INSTALL_DIR = os.getcwd()

    init_tempdir()
    # Initialize grading session and fetch courses
    grader = PyCanvasGrader()

    prefs = load_prefs()
    grader.course_id, grader.assignment_id = startup(grader, prefs)

    if not prefs['session'].get('ignore_cache') and os.path.exists(grader.cache_file):
        last_modified = datetime.fromtimestamp(os.path.getmtime(grader.cache_file))
        print('Found a cached version of this assignment from',
              '{:%b %d, %Y at %I:%M %p.}'.format(last_modified))
        print('Would you like to load it? (y or n)')
        if choose_bool():
            try:
                test_skeleton, users = load_state(grader.course_id, grader.assignment_id)
            except:
                print('This cache is invalid, it will not be loaded.')
                grade_assignment(grader, prefs)
            else:
                print('Loaded cached version of this grading session.')
                CURRENTLY_SAVED = True
                while True:
                    main_menu(grader, test_skeleton, users, prefs)
        else:
            grade_assignment(grader, prefs)
    else:
        grade_assignment(grader, prefs)


if __name__ == '__main__':
    if RUN_WITH_TESTS or ONLY_RUN_TESTS:
        py.test.cmdline.main()
    if not ONLY_RUN_TESTS:
        main()
