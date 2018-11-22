import os
import time
import shutil
from enum import Enum, auto
from io import StringIO
from numbers import Real
from typing import List, Optional, Tuple

import requests
import attr

from .testing import TestSkeleton


CANVAS_API_URL = "https://sit.instructure.com/api/v1"


class Enrollment(Enum):
    """
    Each enrollment type possible in the Canvas API.
    """

    teacher = auto()
    student = auto()
    ta = auto()
    observer = auto()
    designer = auto()

    # override the __str__ to omit "Enrollment."
    def __str__(self):
        return self.name


@attr.s(cmp=False, auto_attribs=True)
class PyCanvasGrader:
    """
    A PyCanvasGrader object; responsible for communicating with the Canvas API
    """

    course_id: int = -1
    assignment_id: int = -1

    token: str = attr.ib(init=False, repr=False)
    session: requests.Session = attr.ib(
        attr.Factory(requests.Session), init=False, repr=False
    )

    def __attrs_post_init__(self):
        self.token = self.authenticate()
        self.session.headers.update({"Authorization": "Bearer " + self.token})

    @staticmethod
    def authenticate() -> str:  # type: ignore
        """
        Responsible for retrieving the OAuth2 token for the session.
        :return: The OAuth2 token

        TODO Talk about "proper" OAuth2 authentication
        """
        try:
            with open("access.token", "r", encoding="UTF-8") as access_file:
                for line in access_file:
                    token = line.strip()
                    if len(token) > 2:
                        return token
        except FileNotFoundError:
            print(
                "Could not find an access.token file. You must place your Canvas OAuth token in a file named\
             'access.token', in this directory."
            )
            exit(1)

    def close(self):
        self.session.close()

    def courses(self, enrollment_type: Enrollment = None) -> list:
        """
        :param enrollment_type: (Optional) teacher, student, ta, observer, designer
        :return: A list of the user's courses as dictionaries, optionally filtered by enrollment_type
        """
        url = f"{CANVAS_API_URL}/courses?per_page=100"
        if enrollment_type is not None:
            url += "&enrollment_type=" + enrollment_type.name.lower()

        response = self.session.get(url)
        return response.json()

    def assignments(self, ungraded: bool = True) -> list:
        """
        :param ungraded: Whether to filter assignments by only those that have ungraded work. Default: True
        :return: A list of the course's assignments
        """
        url = f"{CANVAS_API_URL}/courses/{self.course_id}/assignments?per_page=100"
        if ungraded:
            url += "&bucket=ungraded"

        response = self.session.get(url)
        return response.json()

    def submissions(self) -> list:
        """
        :return: A list of the assignment's submissions
        """
        url = (
            f"{CANVAS_API_URL}/courses/{self.course_id}"
            f"/assignments/{self.assignment_id}/submissions?per_page=100"
        )

        response = self.session.get(url)
        final_response = response.json()
        while response.links.get("next"):
            response = self.session.get(response.links["next"]["url"])
            final_response.extend(response.json())

        return final_response

    def submission(self, user_id: int) -> dict:
        """
        Get information about a single submission
        :param user_id: The user ID of the user whose submission is to be requested
        :return: A dictionary which represents the submission object
        """
        url = (
            f"{CANVAS_API_URL}/courses/"
            f"{self.course_id}/assignments/{self.assignment_id}/submissions/{user_id}"
        )

        response = self.session.get(url)
        return response.json()

    def download_submission(self, submission: dict) -> bool:
        """
        Attempts to download the attachments for a given submission.
        :param submission: The submission dictionary
        :return: True if the request succeeded, False otherwise
        """

        try:
            user_id = submission["user_id"]
            attachments = submission["attachments"]
        except (KeyError, TypeError):
            return False

        # First download everything to .new,
        # then clear .temp/user_id,
        # then move from .new to .temp/user_id.
        # This ensures that the download is complete before overwriting.
        try:
            os.chdir(os.environ["INSTALL_DIR"])
            os.makedirs(os.path.join(".temp", str(user_id), ".new"), exist_ok=True)
            os.chdir(os.path.join(".temp", str(user_id), ".new"))

            for attachment in attachments:
                try:
                    url = attachment["url"]
                    filename = attachment["filename"]
                except (KeyError, TypeError):
                    return False

                r = self.session.get(url, stream=True)
                with open(filename, "wb") as f:
                    for chunk in r.iter_content(chunk_size=1024):
                        if chunk:
                            f.write(chunk)

            os.chdir("..")
            for cur_file in os.listdir("."):
                if os.path.isfile(cur_file):
                    os.remove(cur_file)

            os.chdir(".new")
            for cur_file in os.listdir("."):
                shutil.move(cur_file, "..")
            os.chdir("..")
            os.rmdir(".new")
        except:
            print("Unable work with files in the installation directory")
            print("The program will likely not work as intended.")
            print(
                "Please close the program, ensure that it has permission to read and write in the current directory, and retry."
            )
            return False
        return True

    def user(self, user_id: int) -> dict:
        """
        :param user_id: The ID of the user
        :return: A dictionary with the user's information
        """
        url = f"{CANVAS_API_URL}/courses/{self.course_id}/users/{user_id}"

        response = self.session.get(url)
        return response.json()

    def grade_submission(self, user_id: int, grade: Real):
        if grade is None:
            grade = "NaN"
        url = (
            f"{CANVAS_API_URL}/courses/{self.course_id}/assignments/{self.assignment_id}"
            f"submissions/{user_id}/?submission[posted_grade]={grade}"
        )

        response = self.session.put(url)
        return response.json()

    def grade_submissions(
        self, user_ids_and_grades: List[Tuple[int, int, str]]
    ) -> bool:
        url = (
            f"{CANVAS_API_URL}/courses/"
            f"{self.course_id}/assignments/{self.assignment_id}/submissions/update_grades"
        )

        data = {}
        for user_id, grade, comment in user_ids_and_grades:
            grade = grade if grade is not None else "NaN"

            data[f"grade_data[{user_id}][posted_grade]"] = str(grade)

            if comment != "":
                data[f"grade_data[{user_id}][text_comment]"] = comment

        response = self.session.post(url, data=data)

        status = response.json()
        status_url = f'{CANVAS_API_URL}/progress/{status["id"]}'
        while status["workflow_state"] != "completed":
            if status["workflow_state"] == "failed":
                return False
            time.sleep(0.25)
            response = self.session.get(status_url)
            status = response.json()

        return True

    def comment_on_submission(self, user_id: int, comment: str):
        url = (
            f"{CANVAS_API_URL}/courses/{self.course_id}/assignments/{self.assignment_id}"
            f"/submissions/{user_id}/?comment[text_comment]={comment}"
        )

        response = self.session.put(url)
        return response.json()

    def message_user(self, recipient_id: int, body: str, subject: str = None):
        url = f"{CANVAS_API_URL}/conversations/"

        data = {"recipients[]": recipient_id, "body": body, "subject": subject}
        response = self.session.post(url, data=data)
        return response.json()

    @property
    def cache_file(self):
        """
        Cache file to use for the current course/assignment combination
        """
        file = os.path.join(
            os.environ["INSTALL_DIR"],
            ".cache",
            str(self.course_id),
            str(self.assignment_id),
        )
        return os.path.abspath(file)


@attr.s(auto_attribs=True)
class User:
    user_id: int
    submission_id: int
    name: str
    email: str
    last_posted_grade: Real
    grade_matches_submission: bool
    attempt: int
    grade: Optional[Real] = None
    comment: str = ""
    # Used like a StringBuilder in Java to more efficiently build large strings.
    # But also fulfills the file protocol in Python so is writable like a file.
    log: StringIO = attr.ib(default=attr.Factory(StringIO), init=False, repr=False)

    def __attrs_post_init__(self):
        if self.grade is None:
            self.grade = self.last_posted_grade

    def __str__(self):
        grade = "ungraded" if self.grade is None else self.grade
        submit_status = "posted" if self.submitted else "not posted"
        if not self.grade_matches_submission:
            submit_status += " - needs re-grading (new submission)"
        email = f"({self.email})" if self.email else ""
        return "{} {}: {} [{}]".format(self.name, email, grade, submit_status)

    @property
    def submitted(self):
        return self.grade == self.last_posted_grade

    def grade_self(self, test_skeleton: "TestSkeleton"):
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
        if new_submission["attempt"] > self.attempt:
            if grader.download_submission(new_submission):
                # noinspection PyArgumentList
                self.submission_id = new_submission["id"]
                self.last_posted_grade = new_submission["score"]
                self.grade_matches_submission = new_submission[
                    "grade_matches_current_submission"
                ]
                self.attempt = new_submission["attempt"]
                return True
        return False

    def to_json(self):
        """
        Cache the user as a JSON-compatible dictionary
        """
        attributes = attr.asdict(self)
        attributes["log"] = self.log.getvalue()
        return attributes

    @classmethod
    def from_json(cls, jsonobj):
        """
        Create a User object from a dictionary
        """
        try:
            log = jsonobj.pop("log")
            user = cls(**jsonobj)
        except KeyError as e:
            raise ValueError('Invalid dictionary for caching type "User"') from e
        else:
            user.log.write(log)
            return user
