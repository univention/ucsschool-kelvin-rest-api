from locust import task
from locust_files.base import KelvinClient

URL_NAME = f"{KelvinClient.base_path}/schools/"


class GetAllSchools(KelvinClient):
    @task
    def get_all_schools(self):
        with self.client.rename_request(URL_NAME):
            url = f"{self.base_url}/schools/"
            self.request("get", url, response_codes=[200])
