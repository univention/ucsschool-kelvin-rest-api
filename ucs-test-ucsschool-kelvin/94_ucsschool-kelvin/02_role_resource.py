#!/usr/share/ucs-test/runner python3
## -*- coding: utf-8 -*-
## desc: test operations on role resource
## tags: [ucs_school_kelvin]
## exposure: dangerous
## packages: []
## bugs: []

from __future__ import unicode_literals

import logging
from unittest import TestCase, main

import requests

from ucsschool.importer.utils.ldap_connection import get_admin_connection
from univention.testing.ucsschool.kelvin_api import RESOURCE_URLS, HttpApiUserTestBase

try:
    from urlparse import urljoin  # py2
except ImportError:
    from urllib.parse import urljoin  # py3


logger = logging.getLogger("univention.testing.ucsschool")


class Test(TestCase):
    @classmethod
    def setUpClass(cls):
        cls.lo, _po = get_admin_connection()
        cls.auth_headers = {"Authorization": "{} {}".format(*HttpApiUserTestBase.get_token())}
        print("*** auth_headers={!r}".format(cls.auth_headers))

    def test_01_list_unauth_connection(self):
        response = requests.get(RESOURCE_URLS["roles"])
        self.assertEqual(
            response.status_code,
            401,
            "response.status_code = {} for URL {!r} -> {!r}".format(
                response.status_code, response.url, response.text
            ),
        )

    def test_02_list_auth_connection(self):
        response = requests.get(RESOURCE_URLS["roles"], headers=self.auth_headers)
        self.assertEqual(
            response.status_code,
            200,
            "response.status_code = {} for URL {!r} -> {!r}".format(
                response.status_code, response.url, response.text
            ),
        )
        res = response.json()
        self.assertIsInstance(res, list)
        self.assertSequenceEqual(
            res,
            [
                {
                    "name": "staff",
                    "display_name": "staff",
                    "url": "{}staff".format(RESOURCE_URLS["roles"]),
                },
                {
                    "name": "student",
                    "display_name": "student",
                    "url": "{}student".format(RESOURCE_URLS["roles"]),
                },
                {
                    "name": "teacher",
                    "display_name": "teacher",
                    "url": "{}teacher".format(RESOURCE_URLS["roles"]),
                },
            ],
        )

    def test_04_get_existing_roles(self):
        response = requests.get(RESOURCE_URLS["roles"], headers=self.auth_headers)
        self.assertEqual(
            response.status_code,
            200,
            "response.status_code = {} for URL {!r} -> {!r}".format(
                response.status_code, response.url, response.text
            ),
        )
        res = response.json()
        self.assertIsInstance(res, list)
        self.assertIsInstance(res[0], dict)

        expected_roles = ["staff", "student", "teacher"]
        for attrs in res:
            self.assertIn(attrs["name"], expected_roles, "Unknown role {!r}.".format(attrs["name"]))
            expected_roles.remove(attrs["name"])
        self.assertSequenceEqual(
            expected_roles, [], "Role(s) {!r} were not returned in listing.".format(expected_roles)
        )

        for role in ("staff", "student", "teacher"):
            response = requests.get(urljoin(RESOURCE_URLS["roles"], role), headers=self.auth_headers)
            res = response.json()
            self.assertEqual(
                response.status_code,
                200,
                "response.status_code = {} for URL {!r} -> {!r}".format(
                    response.status_code, response.url, response.text
                ),
            )
            self.assertEqual(res["name"], role, "Expected {!r}, got res={!r}".format(role, res))


if __name__ == "__main__":
    main(verbosity=2)
