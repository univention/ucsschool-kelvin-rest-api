from locust import task
from ucs_test_ucsschool_kelvin_performance.base import KelvinClient

URL_NAME = f"{KelvinClient.base_path}/schools/"


class GetAllSchools(KelvinClient):
    @task
    def get_all_schools(self):
        with self.client.rename_request(URL_NAME):
            url = f"{self.base_url}/schools/"
            _ = self.request("get", url, response_codes=[200])


class GetSchool(KelvinClient):
    @task
    def get_school(self):
        school = self.test_data.random_school()
        with self.client.rename_request(URL_NAME):
            url = f"{self.base_url}/schools/{school}"
            _ = self.request("get", url, response_codes=[200])


class HeadSchool(KelvinClient):
    @task
    def head_school(self):
        school = self.test_data.random_school()
        with self.client.rename_request(URL_NAME):
            url = f"{self.base_url}/schools/{school}"
            _ = self.request("head", url, response_codes=[200])
