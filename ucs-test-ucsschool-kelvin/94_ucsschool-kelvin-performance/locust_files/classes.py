import logging

from locust import task
from ucs_test_ucsschool_kelvin_performance.base import KelvinClient

URL_NAME = f"{KelvinClient.base_path}/classes/"
logger = logging.getLogger(__name__)


class GetAllClasses(KelvinClient):
    @task
    def get_class(self):
        school = self.test_data.random_school()
        with self.client.rename_request(URL_NAME):
            url = f"{self.base_url}/classes/?school={school}"
            _ = self.request("get", url, response_codes=[200])


class GetClass(KelvinClient):
    @task
    def get_class(self):
        school = self.test_data.random_school()
        school_class = self.test_data.random_class(school)
        with self.client.rename_request(URL_NAME):
            url = f"{self.base_url}/classes/{school}/{school_class}"
            _ = self.request("get", url, response_codes=[200])
