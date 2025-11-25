#!/usr/share/ucs-test/runner /usr/bin/pytest-3 -l -v
## -*- coding: utf-8 -*-
## desc: Test that openapi_client_udm module is installed if missing
## tags: [ucs_school_kelvin]
## exposure: dangerous
## packages: []
## bugs: []

import subprocess
import time

import pytest


def test_openapi_udm_client_not_installed():
    """Test that openapi_client_udm is installed automatically

    univention/dev/education/ucsschool-kelvin-rest-api#176
    This test can be removed when the new UDM REST client is used.
    """
    for command in [
        "univention-app shell ucsschool-kelvin-rest-api python -c 'import openapi_client_udm'",
        "univention-app shell ucsschool-kelvin-rest-api pip uninstall --yes openapi_client_udm",
    ]:
        _ = subprocess.run(command, shell=True, check=True)  # nosec

    with pytest.raises(subprocess.CalledProcessError):
        _ = subprocess.run(  # nosec
            "univention-app shell ucsschool-kelvin-rest-api python -c 'import openapi_client_udm'",
            shell=True,
            check=True,
        )

    _ = subprocess.run(  # nosec
        "univention-app restart ucsschool-kelvin-rest-api", shell=True, check=True
    )
    time.sleep(10)

    proc = None
    for _ in range(5):
        proc = subprocess.run(  # nosec
            "univention-app shell ucsschool-kelvin-rest-api python -c 'import openapi_client_udm'",
            shell=True,
            check=False,
        )
        if proc.returncode == 0:
            break
        time.sleep(5)

    assert proc is not None
    assert proc.returncode == 0
