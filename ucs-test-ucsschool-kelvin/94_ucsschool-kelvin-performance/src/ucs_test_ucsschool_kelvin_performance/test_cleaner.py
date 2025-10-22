import concurrent.futures
import logging
import multiprocessing
import time
from collections import deque
from functools import lru_cache

import requests

from .auth import retrieve_token
from .settings_locust import get_settings

CLEANUP_DELETE_PARALLELISM = multiprocessing.cpu_count()

logger = logging.getLogger(__name__)


class TestCleaner:
    base_path = "/ucsschool/kelvin/v1"

    def __init__(self):
        """Please use `get_test_cleaner()` to make sure there is only one instance."""
        self.settings = get_settings()
        self._users_to_delete: deque = deque()

    def delete_user_later(self, username: str):
        self._users_to_delete.append(username)

    def delete(self):
        logger.info(
            "Removing %d users (%r in parallel)...",
            len(self._users_to_delete),
            CLEANUP_DELETE_PARALLELISM,
        )
        auth_token = retrieve_token(
            self.settings.kelvin_host, self.settings.kelvin_username, self.settings.kelvin_password
        )
        headers = {
            "Accept": "application/json",
            "Accept-Language": "en-US",
            "Authorization": auth_token.token,
        }

        def del_user(user_name: str) -> None:
            url = f"https://{self.settings.kelvin_host}{self.base_path}/users/{user_name}"
            response = requests.delete(url, headers=headers)
            if response.status_code == 404:
                logger.info("User %r didn't exist.", user_name)
            elif response.status_code != 204:
                logger.warning(
                    "Deleting user %r failed with %r / %r.",
                    user_name,
                    response.status_code,
                    response.content,
                )
            else:
                logger.info("Removed user %r.", user_name)

        t0 = time.time()
        with concurrent.futures.ThreadPoolExecutor(max_workers=CLEANUP_DELETE_PARALLELISM) as executor:
            for user_name in self._users_to_delete:
                executor.submit(del_user, user_name)
        td = time.time() - t0
        logger.info(
            "Deleted %d users in %.2f sec (%.2f/s)",
            len(self._users_to_delete),
            td,
            len(self._users_to_delete) / td,
        )


@lru_cache(maxsize=1)
def get_test_cleaner() -> TestCleaner:
    return TestCleaner()
