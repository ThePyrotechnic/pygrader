import re
import os
import shutil
import sys
from datetime import datetime
from typing import Sequence, Callable, TypeVar, Union


NUM_REGEX = re.compile(r"-?\d+\.\d+|-?\d+")

T = TypeVar("T")


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


# def list_choices(
#     choices: Sequence[T],
#     message: str = None,
#     formatter: Callable[[T], str] = str,
#     msg_below: bool = False,
#     start_at: int = 1,
# ):
#     if not msg_below and message is not None:
#         print(message)

#     for i, choice in enumerate(choices, start_at):
#         print(i, formatter(choice), sep=".\t")

#     if msg_below and message is not None:
#         print(message)


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
