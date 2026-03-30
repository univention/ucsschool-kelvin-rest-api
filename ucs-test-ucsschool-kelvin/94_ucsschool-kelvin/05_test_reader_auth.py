#!/usr/share/ucs-test/runner /usr/bin/pytest-3 -l -v
## -*- coding: utf-8 -*-
## desc: test operations on school resource
## tags: [ucs_school_kelvin]
## exposure: dangerous
## packages: []
## bugs: []

import pytest
import requests

from univention.testing.ucsschool.kelvin_api import RESOURCE_URLS

# See also: In container tests test_auth_reader.py which are more comprehensive.


def test_get_accepted(auth_header_reader):
    response = requests.get(
        RESOURCE_URLS["users"], headers=auth_header_reader, params={"school": "DEMOSCHOOL"}
    )
    assert response.status_code == 200


def test_head_accepted(auth_header_reader):
    response = requests.head(f"{RESOURCE_URLS['schools']}/DEMOSCHOOL", headers=auth_header_reader)
    assert response.status_code == 200


@pytest.mark.parametrize("method", [requests.patch, requests.delete, requests.put, requests.post])
def test_write_rejected(auth_header_reader, method):
    response = method(
        f"{RESOURCE_URLS['users']}/{'demo_student' if method is not requests.post else ''}",
        headers=auth_header_reader,
    )
    assert response.status_code == 401
