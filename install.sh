#!/bin/bash

# Basic install script for setting up the grader
# TODO Translate this file into a setup.py and make
# the grader pip-installable.

python3 -m pip install pipenv
python3 -m pipenv activate
pipenv update
chmod +x pycanvasgrader.py
echo -n "Enter your Canvas API token: " && read token
echo ${token} > access.token
