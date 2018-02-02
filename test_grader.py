"""
Unit tests for PyCanvasGrader
"""
# built-ins
import json

# 3rd-party
import requests

# package-specific
from .pycanvasgrader import PyCanvasGrader


class TestGrader:
    def test_authenticate(self):
        """
        Make sure the authentication function returns a valid key
        """
        token = PyCanvasGrader().authenticate()
        s = requests.Session()
        r = s.get('https://canvas.instructure.com/api/v1/courses', headers={'Authorization': 'Bearer ' + token})
        resp = json.loads(r.text)
        assert type(resp) == list and resp[0].get('id') is not None

    def test_courses(self):
        """
        Make sure that courses() always returns a list
        """
        g = PyCanvasGrader()
        courses = g.courses('designer')
        assert type(courses) == list

    def test_assignments(self):
        """
        Make sure that assignments() always returns a list
        """
        g = PyCanvasGrader()
        course_id = g.courses('teacher')[0].get('id')
        assert type(g.assignments(course_id, ungraded=False)) == list

    def test_submissions(self):
        """
        Make sure that submissions() always returns a list
        """
        g = PyCanvasGrader()
        course_id = g.courses('teacher')[0].get('id')
        assignment_id = g.assignments(course_id, ungraded=False)[0].get('id')
        assert type(g.submissions(course_id, assignment_id)) == list
