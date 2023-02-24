from locust import task
from locust_files.base import KelvinClient

URL_NAME = f"{KelvinClient.base_path}/users/"


class GetUser(KelvinClient):
    @task
    def get_user(self):
        school = self.test_data.random_school()
        username = self.test_data.random_user(school)
        with self.client.rename_request(URL_NAME):
            url = f"{self.base_url}/users/{username}"
            self.request("get", url, response_codes=[200])
