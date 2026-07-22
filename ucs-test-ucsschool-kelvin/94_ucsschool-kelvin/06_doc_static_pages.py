#!/usr/share/ucs-test/runner /usr/bin/pytest-3 -l -v
## -*- coding: utf-8 -*-
## desc: /changelog and /readme serve the static HTML built into the Kelvin image
## tags: [ucs_school_kelvin]
## exposure: dangerous
## packages: []
## bugs: []

import subprocess
from urllib.parse import urljoin

import pytest
import requests

from univention.testing.ucsschool.kelvin_api import API_ROOT_URL, API_ROOT_URL_V2

APP = "ucsschool-kelvin-rest-api"
STATIC_DIR = "/kelvin/kelvin-api/static"


def _file_in_container(name: str) -> str:
    """Return the contents of a file inside the running Kelvin container."""
    result = subprocess.run(  # nosec
        ["univention-app", "shell", APP, "cat", "{}/{}".format(STATIC_DIR, name)],
        check=True,
        capture_output=True,
        text=True,
    )
    return result.stdout


@pytest.mark.parametrize("root_url", [API_ROOT_URL, API_ROOT_URL_V2])
@pytest.mark.parametrize("endpoint", ["changelog", "readme"])
def test_static_doc_endpoint_matches_file_on_disk(root_url: str, endpoint: str) -> None:
    """The endpoint is reachable and serves exactly the file built into the image."""
    url = urljoin(root_url, endpoint)
    response = requests.get(url, verify=False)  # nosec
    assert response.status_code == 200, "{!r} -> [{}] {!r}".format(
        url, response.status_code, response.text
    )
    assert response.headers["content-type"].startswith("text/html")
    assert response.text == _file_in_container("{}.html".format(endpoint))
