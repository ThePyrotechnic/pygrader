# PyGrader

An automatic grader for programming assignments on Canvas. The grader can be used as a wrapper around existing
test scripts with ideally minimal refactoring.

# Requirements

- Python 3.6
- Requests
- py (optional; for unit tests) 

# Installing

The requirements to the PyCanvasGrader script are
- [Python 3.6 interpreter](https://www.python.org/downloads/release/python-364/)
- A Canvas access token
  This can be found by going to `Account/Settings` in Canvas and going to the button that says
  `+ New Access Token`. More information can be found at [here](https://community.canvaslms.com/docs/DOC-10806-4214724194)
- A [skeleton](#Skeletons) to configure the grader to run the tests.

Once you have installed a Python3.6 interpreter, you can install/configure the grader by following 
the shell example below.
```bash
git clone https://github.com/ThePyrotechnic/pygrader.git
cd pygrader
python3.6 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
chmod +x pycanvasgrader.py
# In the following commands replace $EDITOR with your editor of choice.
$EDITOR access.token         # Paste the token into the file.
$EDITOR skeletons/$SKELETON  # replace $SKELETON with the filename you want for the skeleton
./pycanvasgrader.py          # start the grader
```

> __Note__: PyCanvasGrader works best with Python virtual environments. Make sure that you always
  have the virtualenv activated before running the PyCanvasGrader.

# Skeletons

The grader can be configured using what are called _skeletons_. These are configuration files written
either in JSON or TOML which tell the grader how to grade submissions. They control things like:
- Point values for each test
- Proper output matching
- Automatic timeouts

A common use pattern is to write an test script which the grader then uses to determine points.

Below is a sample skeleton written using the TOML format, which tests a simple
C program with the expected behavior of `./hello <name>` printing `Hello, <name>!`.

```toml
# What the skeleton selection menu in the grader will call this skeleton
descriptor = "./hello tests"

# Disables the grader from committing to Canvas
disarm = true

[default]
# Defaults which all test cases will inherit unless overridden
command = "./hello"
exact_match = false
point_val = 5

[tests.compile]
command = "gcc"
args = ["%s", "-o", "hello"]
point_val = 10  # override the point_val from 5 to 10

[tests.joe]
args = ["joe"]
output_match = "Hello, Joe!"

[tests.world]
args = ["World"]
output_match = "Hello, World!"
```

# Contributing

Please fork this repository and create pull requests. A single pull request should solve a single issue or fix a single feature.
Do not hesitate to create issues for bugs or feature requests.
