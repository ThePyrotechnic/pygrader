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
import json
import os
import shutil
import signal
import sys
from importlib import util
from datetime import datetime
from typing import List

# 3rd-party
import toml

# library
from lib.canvas_api import Enrollment, PyCanvasGrader, User, TestSkeleton
from lib.canvas_api import utils

from lib.core import choices, preferences

if util.find_spec("py"):
    import py

# globals
RUN_WITH_TESTS = False
ONLY_RUN_TESTS = False
os.environ["INSTALL_DIR"] = "."
CURRENTLY_SAVED = False


PREFERENCES_FILE = "preferences.toml"


def close_program(grader: PyCanvasGrader, restart=False):
    grader.close()
    if restart:
        init_tempdir()
        main()
    exit(0)


def init_tempdir():
    try:
        os.chdir(os.environ["INSTALL_DIR"])
        if os.path.exists(".temp"):
            shutil.rmtree(".temp")
        os.makedirs(".temp", exist_ok=True)
    except:
        print(
            'An error occurred while initializing the "temp" directory.',
            "Please delete/create the directory manually and re-run the program",
        )
        exit(1)


def load_preferences() -> dict:
    """
    Load preferences for grader execution
    """
    preferences = {}
    try:
        with open("preferences.toml", "r") as pref_file:
            preferences = toml.load(pref_file)
    except (FileNotFoundError, IOError):
        pass
    except toml.TomlDecodeError:
        print("Preference file is invalid. Is it valid TOML?", file=sys.stderr)

    # To simplify logic elsewhere, prefs[category] for expected categories
    # should be defined
    return {
        "session": preferences.get("session", {}),
        "quickstart": preferences.get("quickstart", {}),
    }


def save_prefs(prefs: dict, new_prefs: dict):
    prefs = {**prefs, **new_prefs}
    try:
        with open("preferences.toml", mode="w") as prefs_file:
            toml.dump(prefs, prefs_file)
    except IOError:
        print("Unable to write preferences.toml")


def choose_course(course_list) -> int:
    return choices.choose(
        course_list,
        "Choose a course from the following list:",
        formatter=lambda c: "%s (%s)"
        % (c.get("name"), utils.month_year(c["start_at"])),
    ).get("id")


def choose_assignment(assignment_list) -> int:
    return choices.choose(
        assignment_list,
        "Choose an assignment to grade:",
        formatter=lambda assignment: assignment.get("name"),
    ).get("id")


def save_state(grader: PyCanvasGrader, test_skeleton: TestSkeleton, users: List[User]):
    global CURRENTLY_SAVED
    utils.print_on_curline("Saving state...")
    try:
        os.chdir(os.environ["INSTALL_DIR"])
        cache_dir = os.path.join(
            ".cache", str(grader.course_id), str(grader.assignment_id)
        )
        os.makedirs(cache_dir, exist_ok=True)
        os.chdir(cache_dir)

        if os.path.exists(".temp"):
            shutil.rmtree(".temp")
        shutil.copytree(os.path.join(os.environ["INSTALL_DIR"], ".temp"), ".temp")

        with open(".cachefile", mode="w") as cache_file:
            json.dump(
                {
                    "skeleton": test_skeleton.to_json(),
                    "users": [user.to_json() for user in users],
                },
                cache_file,
            )

        utils.print_on_curline("State saved.    \n")
        CURRENTLY_SAVED = True
        os.chdir(os.environ["INSTALL_DIR"])
    except:
        print("There was an error while saving the state.")
        print(
            "Make sure the program has permission to read/write in {}".format(
                os.path.join(os.environ["INSTALL_DIR"], ".cache")
            )
        )
        print("and that the directory is not in use.")
        os.chdir(os.environ["INSTALL_DIR"])


def load_state(course_id: int, assignment_id: int):
    os.chdir(os.environ["INSTALL_DIR"])
    if os.path.exists(".temp"):
        shutil.rmtree(".temp")

    os.chdir(os.path.join(".cache", str(course_id), str(assignment_id)))
    shutil.copytree(".temp", os.path.join(os.environ["INSTALL_DIR"], ".temp"))
    with open(".cachefile") as cache_file:
        cache = json.load(cache_file)
        test_skeleton = TestSkeleton.from_json(cache["skeleton"])
        users = [User.from_json(userdata) for userdata in cache["users"]]

        os.chdir(os.environ["INSTALL_DIR"])
        return test_skeleton, users


def grade_all_submissions(
    test_skeleton: TestSkeleton, users: List[User], only_ungraded: bool = False
) -> bool:
    if only_ungraded:
        users = [u for u in users if u.grade is None]
        if len(users) == 0:
            print("No currently ungraded submissions to grade.")
            return False

    total = len(users)

    for count, user in enumerate(users):
        utils.print_on_curline(f"grading ({count}/{total})")
        user.grade_self(test_skeleton)
    utils.print_on_curline(f"grading complete ({total}/{total})\n")
    return True


def submit_all_grades(grader: PyCanvasGrader, users: list) -> bool:
    modified = False
    user_data = []
    for user in users:
        if not user.submitted:
            user_data.append((user.user_id, user.grade, user.comment))
            modified = True
            user.last_posted_grade = user.grade
    if len(user_data) > 0:
        success = grader.grade_submissions(user_data)
        if not success:
            print("Batch grading failed.")
            print("Check your network connection and try again.")
    return modified


def handle_signal(_, frame):
    print("Received interrupt signal.")
    grader = None
    users = None
    test_skeleton = None

    while frame and None in (grader, users, test_skeleton):
        try:
            grader = frame.f_locals["grader"]
            users = frame.f_locals["users"]
            test_skeleton = frame.f_locals["test_skeleton"]
        except KeyError:
            grader, users, test_skeleton = None, None, None
            frame = frame.f_back
        else:
            break

    if grader and users and test_skeleton:
        save_state(grader, test_skeleton, users)


def user_menu(grader: PyCanvasGrader, test_skeleton: TestSkeleton, user: User):
    global CURRENTLY_SAVED

    # This way strings only need to be updated once
    possible_opts = {
        "log": "View test log",
        "rerun": "Re-run tests",
        "run": "Run tests",
        "submit": "Submit this grade",
        "modify": "Modify this user's grade",
        "comment": "View or edit the comment for this grade",
        "clear-comment": "Clear the current comment",
        "update": "Update this user's submission",
        "clear": "Clear this user's grade",
        "back": "Return to the main menu",
    }

    while True:
        options = []
        if user.log.getvalue() != "":
            options.append(possible_opts["rerun"])
            options.append(possible_opts["log"])
        else:
            options.append(possible_opts["run"])
        if not user.submitted or not user.grade_matches_submission:
            options.append(possible_opts["submit"])
        options.append(possible_opts["modify"])
        options.append(possible_opts["comment"])
        if user.comment != "":
            options.append(possible_opts["clear-comment"])
        options.append(possible_opts["update"])
        if user.grade is not None:
            options.append(possible_opts["clear"])
        options.append(possible_opts["back"])

        print("User Menu |", user)
        if not user.submitted:
            if user.last_posted_grade is None:
                print("Last posted grade: ungraded")
            else:
                print("Last posted grade:", user.last_posted_grade)
        print("-")
        choice = choices.choose(options)

        if choice == possible_opts["log"]:
            utils.clear_screen()
            print(user.log.getvalue())
        elif choice in (possible_opts["rerun"], possible_opts["run"]):
            utils.clear_screen()
            grade_before = user.grade
            user.grade_self(test_skeleton)
            if user.grade != grade_before:
                CURRENTLY_SAVED = False
        elif choice == possible_opts["submit"]:
            utils.clear_screen()
            submitted_before = user.submitted
            user.submit_grade(grader)
            if not user.grade_matches_submission:
                user.grade_matches_submission = True
                CURRENTLY_SAVED = False
            if user.submitted != submitted_before:
                CURRENTLY_SAVED = False
        elif choice == possible_opts["modify"]:
            grade_before = user.grade
            print("Enter a new grade: ")
            user.grade = choices.choose_float(
                1000, allow_negative=True, allow_zero=True
            )
            if user.grade != grade_before:
                CURRENTLY_SAVED = False
            utils.clear_screen()
        elif choice == possible_opts["comment"]:
            cur_comment = user.comment
            if cur_comment == "":
                print("This user has no current comment.")
            else:
                print("Current comment:")
                print(user.comment)
            print(
                "Type the new comment below, and press enter twice when you are finished."
            )
            print("Entering a blank comment here will not clear the current comment.")
            inp = utils.multiline_input()
            if inp != "":
                user.comment = inp
                if user.comment != cur_comment:
                    CURRENTLY_SAVED = False
            utils.clear_screen()
        elif choice == possible_opts["clear-comment"]:
            user.comment = ""
            CURRENTLY_SAVED = False
            utils.clear_screen()
        elif choice == possible_opts["update"]:
            utils.clear_screen()
            if user.update(grader):
                CURRENTLY_SAVED = False
                print("A new submission has been downloaded for this user.")
            else:
                print("No available updates for this user.")
        elif choice == possible_opts["clear"]:
            utils.clear_screen()
            grade_before = user.grade
            user.grade = None
            if user.grade != grade_before:
                CURRENTLY_SAVED = False
        elif choice == possible_opts["back"]:
            utils.clear_screen()
            return


def main_menu(
    grader: PyCanvasGrader, test_skeleton: TestSkeleton, users: list, prefs: dict
):
    global CURRENTLY_SAVED

    print("Main Menu\n-")
    utils.list_choices(users)
    print("-")

    options = {
        "grade_all": "Grade all submissions",
        "grade_ungraded": "Grade only ungraded submissions",
        "submit_all": "Submit all grades",
        "reload_skeleton": "Reload test skeleton",
        "save": "Save changes",
        "save_and_quit": "Save and quit",
        "quit": "Quit",
    }

    # Doing it this way preserves order while still only needing to update 1 string if needed
    opt_list = [
        options["grade_all"],
        options["grade_ungraded"],
        options["submit_all"],
        options["reload_skeleton"],
    ]
    if not CURRENTLY_SAVED:
        opt_list.append(options["save"])
        opt_list.append(options["save_and_quit"])

    opt_list.append(options["quit"])

    utils.list_choices(
        opt_list,
        (
            "Choose a user to work with that user individually,\n"
            "or enter an action from the menu above."
        ),
        msg_below=True,
        start_at=len(users) + 1,
    )

    choice = choices.choose_int(len(opt_list) + len(users))

    if choice <= len(users):
        utils.clear_screen()
        user_menu(grader, test_skeleton, users[choice - 1])
    else:
        selection = opt_list[choice - len(users) - 1]
        if selection == options["grade_all"]:
            utils.clear_screen()
            success = grade_all_submissions(test_skeleton, users)
            if success and not prefs["session"].get("disable_autosave"):
                save_state(grader, test_skeleton, users)
            elif success:
                CURRENTLY_SAVED = False
        elif selection == options["grade_ungraded"]:
            utils.clear_screen()
            success = grade_all_submissions(test_skeleton, users, only_ungraded=True)
            if success and not prefs["session"].get("disable_autosave"):
                save_state(grader, test_skeleton, users)
            elif success:
                CURRENTLY_SAVED = False
        elif selection == options["submit_all"]:
            utils.clear_screen()
            modified = submit_all_grades(grader, users)
            if modified:
                CURRENTLY_SAVED = False
        elif selection == options["reload_skeleton"]:
            utils.clear_screen()
            if not test_skeleton.reload():
                print(
                    "There was an error reloading this skeleton. It has not been reloaded."
                )
                print(
                    "Double-check the file's syntax, and make sure there are no typos."
                )
            else:
                print("Successfully reloaded the test skeleton.")
                CURRENTLY_SAVED = False
        elif selection == options["save"]:
            utils.clear_screen()
            if not CURRENTLY_SAVED:
                save_state(grader, test_skeleton, users)
            else:
                print("Nothing to save.")
        elif selection == options["save_and_quit"]:
            if not CURRENTLY_SAVED:
                save_state(grader, test_skeleton, users)
            close_program(grader)
        elif selection == options["quit"]:
            if not CURRENTLY_SAVED:
                print("You have unsaved changes in the current grading session.")
                print("Would you like to save them before quitting? (y or n)")
                if choices.choose_bool():
                    save_state(grader, test_skeleton, users)

            close_program(grader)


def startup(grader: PyCanvasGrader, prefs: dict) -> (int, int):
    session = prefs["session"]
    quickstart = prefs["quickstart"]

    role_str = quickstart.get("role")
    if isinstance(role_str, str):
        role_str = role_str.lower()
    try:
        selected_role = Enrollment[role_str]
    except KeyError:
        selected_role = Enrollment[
            choices.choose(["teacher", "ta"], "Choose a class role to filter by:")
        ]

    courses = grader.courses(selected_role)
    if not courses:
        input("No courses were found for the selected role. Press enter to restart")
        close_program(grader, restart=True)

    course_id = quickstart.get("course_id")
    if not course_id or not isinstance(course_id, int):
        course_id = choose_course(courses)
    else:
        # must validate course_id from preferences file
        valid = any(c.get("id") == course_id for c in courses)
        if not valid:
            course_id = choose_course(courses)

    grader.course_id = course_id

    if not session.get("no_save_prompt") and (
        not quickstart.get("course_id") or not quickstart.get("role")
    ):
        print("Save these settings for faster startup next time? (y or n):")
        if choices.choose_bool():
            with open(PREFENCES_FILE, "w") as pf:
                prefs.update(
                    {"quickstart": {"role": selected_role.name, "course_id": course_id}}
                )
                preferences.dump(prefs, pf)

    assignments = grader.assignments(ungraded=False)
    if not assignments:
        input("No assignments were found. Press enter to restart")
        close_program(grader, restart=True)

    assignment_id = quickstart.get("assignment_id")
    if not assignment_id or not type(assignment_id) == int:
        assignment_id = choose_assignment(assignments)
    else:
        # must validate assignment_id from preferences file
        valid = any(a.get("id") == assignment_id for a in assignments)
        if not valid:
            assignment_id = choose_assignment(assignments)

    grader.assignment_id = assignment_id

    return course_id, assignment_id


def grade_assignment(grader: PyCanvasGrader, prefs: dict):
    session = prefs["session"]
    quickstart = prefs["quickstart"]

    # Get list of submissions for this assignment
    submission_list = [
        s for s in grader.submissions() if s.get("workflow_state") != "unsubmitted"
    ]
    if len(submission_list) < 1:
        input("There are no submissions for this assignment. Press enter to restart")
        close_program(grader, restart=True)

    ungraded_only = session.get("only_download_ungraded")
    if ungraded_only is None:
        print("Only download currently ungraded submissions? (y or n):")
        ungraded_only = choices.choose_bool()

    # Create users from submissions
    users = []
    total = len(submission_list)
    failed = 0

    utils.clear_screen()
    for count, submission in enumerate(submission_list):
        if (
            ungraded_only
            and submission["grade_matches_current_submission"]
            and submission["score"] is not None
        ):
            continue
        user_id = submission.get("user_id")
        if submission.get("attachments") is not None:
            utils.print_on_curline(
                "downloading submissions... ({}/{})".format(count, total)
            )
            if grader.download_submission(submission):
                user_data = grader.user(user_id)
                users.append(
                    User(
                        user_id,
                        submission["id"],
                        user_data["name"],
                        user_data.get("email"),
                        submission["score"],
                        submission["grade_matches_current_submission"],
                        submission["attempt"],
                    )
                )
            else:
                failed += 1
    utils.print_on_curline(
        "Submissions downloaded. ({} total, {} failed to validate)\n\n".format(
            total, failed
        )
    )

    if len(users) == 0:
        print("No submissions yet for this assignment.")

    selected_skeleton = None
    if quickstart.get("skeleton"):
        selected_skeleton = TestSkeleton.parse_skeleton(quickstart.get("skeleton"))

    if selected_skeleton is None:
        skeleton_list = TestSkeleton.parse_skeletons(
            os.path.join(os.environ.get("INSTALL_DIR"), "skeletons")
        )
        selected_skeleton = choices.choose(
            skeleton_list,
            "Choose a skeleton to use for grading this assignment:",
            formatter=lambda skel: skel.descriptor,
        )
    if not session.get("disable_autosave"):
        save_state(grader, selected_skeleton, users)

    # Display main menu
    while True:
        main_menu(grader, selected_skeleton, users, prefs)


def main():
    global CURRENTLY_SAVED

    if sys.version_info < (3, 6):
        print("Python 3.6+ is required")
        exit(1)

    signal.signal(signal.SIGINT, handle_signal)

    utils.clear_screen()

    os.environ["INSTALL_DIR"] = os.getcwd()

    init_tempdir()
    # Initialize grading session and fetch courses
    grader = PyCanvasGrader()

    prefs = load_preferences()
    grader.course_id, grader.assignment_id = startup(grader, prefs)

    if not prefs["session"].get("ignore_cache") and os.path.exists(grader.cache_file):
        last_modified = datetime.fromtimestamp(os.path.getmtime(grader.cache_file))
        print(
            "Found a cached version of this assignment from",
            f"{last_modified:%b %d, %Y at %I:%M%p.}",
        )
        print("Would you like to load it? (y or n)")
        if choices.choose_bool():
            try:
                test_skeleton, users = load_state(
                    grader.course_id, grader.assignment_id
                )
            except:
                print("This cache is invalid, it will not be loaded.")
                grade_assignment(grader, prefs)
            else:
                print("Loaded cached version of this grading session.")
                CURRENTLY_SAVED = True
                while True:
                    main_menu(grader, test_skeleton, users, prefs)
        else:
            grade_assignment(grader, prefs)
    else:
        grade_assignment(grader, prefs)


if __name__ == "__main__":
    if RUN_WITH_TESTS or ONLY_RUN_TESTS:
        py.test.cmdline.main()
    if not ONLY_RUN_TESTS:
        main()
