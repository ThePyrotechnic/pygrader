An automatic grader for programming assignments on Canvas.

# Requirements

- Python 3.6
- Requests
- py (optional; for unit tests) 

# Installing

1. Install python 3.6+
2. Run `pip install -r requirements.txt`
3. Create a file in this directory called `access.token` which contains your Canvas API token. see [here](https://community.canvaslms.com/docs/DOC-10806-4214724194) for instructions.
4. Create a skeleton file for your assignment(s) in the `skeletons` directory. (See `documentation.html` and the included examples for more info)
5. Run `python pycanvasgrader.py`

# Contributing

Please fork this repository and create pull requests. A single pull request should solve a single issue or fix a single feature.
Do not hesitate to create issues for bugs or feature requests.