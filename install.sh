#!/bin/bash

# Basic install script for setting up the grader
# TODO Translate this file into a setup.py and make
# the grader pip-installable.

python3.6 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
chmod +x pycanvasgrader.py
# In the following commands replace $EDITOR with your editor of choice.
echo -n "Enter your Canvas API token: " && read token
echo $token > access.token
