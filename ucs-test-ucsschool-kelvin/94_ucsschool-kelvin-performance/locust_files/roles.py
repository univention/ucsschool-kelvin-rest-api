import logging
import random

from locust import task
from ucs_test_ucsschool_kelvin_performance.base import KelvinClient

URL_NAME = f"{KelvinClient.base_path}/roles/"
logger = logging.getLogger(__name__)


class GetRole(KelvinClient):
    @task
    def get_role(self):
        role = random.choice(["staff", "legal_guardian", "student", "teacher", "school_admin"])  # nosec
        with self.client.rename_request(URL_NAME):
            url = f"{self.base_url}/roles/{role}"
            _ = self.request("get", url, response_codes=[200])


class GetAllRoles(KelvinClient):
    @task
    def get_all_roles(self):
        with self.client.rename_request(URL_NAME):
            url = f"{self.base_url}/roles/"
            _ = self.request("get", url, response_codes=[200])
