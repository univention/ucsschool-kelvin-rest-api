#!/usr/share/ucs-test/runner /usr/bin/pytest-3 -l -v
## -*- coding: utf-8 -*-
## desc: Test performance of POST /ucsschool/kelvin/v1/users/
## tags: [kelvin, performance]
## exposure: dangerous
## packages: []
## bugs: []

import random

from locust import task
from locust_files.base import KelvinClient

URL_NAME = f"{KelvinClient.base_path}/users/"


class CreateUser(KelvinClient):
    @task
    def create_user(self):
        name = self.fake.unique.pystr(max_chars=15)
        school = self.test_data.random_school()
        school_class = self.test_data.random_class(school)
        payload = {
            "name": name,
            "firstname": self.fake.first_name(),
            "lastname": self.fake.last_name(),
            "roles": [self.role_url(random.choice(self.settings.roles))],  # nosec
            "password": self.fake.password(length=20),
            "record_uid": name,
            "schools": [self.school_url(school)],
            "school_classes": {school: [school_class]},
            "source_uid": "PERFORMANCE_TEST",
        }
        with self.client.rename_request(URL_NAME):
            url = f"{self.base_url}/users/"
            res = self.request("post", url, json=payload, response_codes=[201])
            if res.status_code < 400:
                self.test_cleaner.delete_user_later(name)
