"""
Functions for loading and saving the preference file.

Does not rely on hard coded files, so that multiple preference files
can be used.
"""
import typing

import toml


def load(fp: typing.TextIO) -> dict:
    """
    Loads the preferences from the file pointer fp.
    """
    try:
        preferences = toml.load(fp)
    except toml.TomlDecodeError:
        preferences = {}

    return {
        "session": preferences.get("session", {}),
        "quickstart": preferences.get("quickstart", {}),
    }


def dump(preferences: dict, fp: typing.TextIO) -> None:
    """
    Write the preferences to a file.
    """
    toml.dump(preferences, fp)
