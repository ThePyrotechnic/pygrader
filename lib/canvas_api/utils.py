import re
import os
import shutil
import sys
from enum import Enum, auto
from datetime import datetime
from typing import Sequence, Callable, TypeVar

import attr


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


NUM_REGEX = re.compile(r"-?\d+\.\d+|-?\d+")

T = TypeVar("T")


def option(default=False):
    """
    Constructor for optional boolean configuartion attributes
    """
    return attr.ib(default=default, type=bool)


def choose_val(
    hi_num: int,
    allow_negative: bool = False,
    allow_zero: bool = False,
    allow_float: bool = False,
) -> int:
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
            i = float(val) if allow_float else int(val)
        except ValueError:
            continue

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
        if b.lower() in {"y", "n", "yes", "no"}:
            return b.startswith(("y", "Y"))


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


def month_year(time_string: str) -> str:
    dt = datetime.strptime(time_string, "%Y-%m-%dT%H:%M:%SZ")
    return dt.strftime("%b %Y")


def get_lines():
    while True:
        # Get every line until the first empty line
        yield from iter(input, "")

        # Get the next line and check if it is empty. If not, continue
        nextline = input()
        if nextline == "":
            break
        else:
            yield nextline


def multiline_input() -> str:
    return "\n".join(get_lines()).rstrip()


def list_choices(
    choices: Sequence[T],
    message: str = None,
    formatter: Callable[[T], str] = str,
    msg_below: bool = False,
    start_at: int = 1,
):
    if not msg_below and message is not None:
        print(message)

    for i, choice in enumerate(choices, start_at):
        print(i, formatter(choice), sep=".\t")

    if msg_below and message is not None:
        print(message)


def choose(
    choices: Sequence[T],
    message: str = None,
    formatter: Callable[[T], str] = str,
    msg_below: bool = False,
) -> T:
    """
    Display the contents of a sequence and have the user enter a 1-based
    index for their selection.

    Takes an optional message to print before showing the choices
    """
    list_choices(choices, message, formatter, msg_below)

    i = choose_val(len(choices), False)
    return choices[i - 1]


def print_on_curline(msg: str):
    sys.stdout.write("\r")
    sys.stdout.flush()
    sys.stdout.write(msg)
    sys.stdout.flush()


def clear_screen():
    """
    Clear the screen.
    """
    os.system("cls" if os.name == "nt" else "clear")
