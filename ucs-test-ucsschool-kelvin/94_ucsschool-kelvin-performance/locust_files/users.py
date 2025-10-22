import logging
import random

from locust import task
from requests.exceptions import JSONDecodeError
from ucs_test_ucsschool_kelvin_performance.base import KelvinClient

URL_NAME = f"{KelvinClient.base_path}/users/"
logger = logging.getLogger(__name__)


class GetAllUsers(KelvinClient):
    @task
    def get_all_users(self):
        school = self.test_data.random_school()
        with self.client.rename_request(URL_NAME):
            url = f"{self.base_url}/users/?school={school}"
            _ = self.request("get", url, response_codes=[200])


class GetUser(KelvinClient):
    @task
    def get_user(self):
        school = self.test_data.random_school()
        username = self.test_data.random_user(school)
        with self.client.rename_request(URL_NAME):
            url = f"{self.base_url}/users/{username}"
            _ = self.request("get", url, response_codes=[200])


class HeadUser(KelvinClient):
    @task
    def head_user(self):
        school = self.test_data.random_school()
        username = self.test_data.random_user(school)
        with self.client.rename_request(URL_NAME):
            url = f"{self.base_url}/users/{username}"
            _ = self.request("head", url, response_codes=[200])


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
            else:
                try:
                    msg = res.json()
                except JSONDecodeError:
                    msg = res.text
                logger.error(
                    "POST %r payload=%r -> [HTTP %d (%s)] %r",
                    url,
                    payload,
                    res.status_code,
                    res.reason,
                    msg,
                )
