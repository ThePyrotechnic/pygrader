"""
Utility functions for prompting the user for input.
"""
from typing import Callable, Sequence, TypeVar, Union


__all__ = ["choose_bool", "choose_int", "choose_float", "choose"]


T = TypeVar("T")


def choose_bool() -> bool:
    """
    Prompt the user yes/no.
    """
    for b in iter(input, None):
        if b.lower() in {"y", "n", "yes", "no"}:  # type: ignore
            return b.startswith(("y", "Y"))  # type: ignore


def choose_float(
    hi_num: int, allow_negative: bool = False, allow_zero: bool = False
) -> Union[int, float]:
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
            f = float(val)  # type: ignore
        except ValueError:
            continue

        if (f < 0 and not allow_negative) or (f == 0 and not allow_zero) or f > hi_num:
            continue

        return f


def choose_int(
    hi_num: int, allow_negative: bool = False, allow_zero: bool = False
) -> int:
    """
    Prompt the user for an integer.
    """
    for val in iter(input, None):
        try:
            i = int(val)  # type: ignore
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


def list_choices(
    choices: Sequence[T],
    message: str = None,
    formatter: Callable[[T], str] = str,
    msg_below: bool = False,
    start_at: int = 1,
):
    """
    Display all choices in a sequence with a specified message.
    """
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

    i = choose_int(len(choices), False)
    return choices[i - 1]
