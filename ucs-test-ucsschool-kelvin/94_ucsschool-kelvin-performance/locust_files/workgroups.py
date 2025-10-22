import logging

from locust import task
from ucs_test_ucsschool_kelvin_performance.base import KelvinClient

URL_NAME = f"{KelvinClient.base_path}/workgroups/"
logger = logging.getLogger(__name__)


class GetAllWorkGroups(KelvinClient):
    @task
    def get_workgroup(self):
        school = self.test_data.random_school()
        with self.client.rename_request(URL_NAME):
            url = f"{self.base_url}/workgroups/?school={school}"
            _ = self.request("get", url, response_codes=[200])


class GetWorkGroup(KelvinClient):
    @task
    def get_workgroup(self):
        school = self.test_data.random_school()
        work_group = self.test_data.random_workgroup(school)
        with self.client.rename_request(URL_NAME):
            url = f"{self.base_url}/workgroups/{school}/{work_group}"
            _ = self.request("get", url, response_codes=[200])
