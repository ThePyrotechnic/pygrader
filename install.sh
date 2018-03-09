#!/bin/bash

# Basic install script for setting up the grader
# TODO Translate this file into a setup.py and make
# the grader pip-installable.

git clone https://github.com/ThePyrotechnic/pygrader.git
cd pygrader
python3.6 -m venv .
source bin/activate
pip install -r requirements.txt
chmod +x pycanvasgrader.py
# In the following commands replace $EDITOR with your editor of choice.
echo -n "Enter your token: " && read token
echo $token > access.token
