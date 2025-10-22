# -*- coding: utf-8 -*-
#
# Copyright 2023 Univention GmbH
#
# http://www.univention.de/
#
# All rights reserved.
#
# The source code of this program is made available
# under the terms of the GNU Affero General Public License version 3
# (GNU AGPL V3) as published by the Free Software Foundation.
#
# Binary versions of this program provided by Univention to you as
# well as other copyrighted, protected or trademarked materials like
# Logos, graphics, fonts, specific documentations and configurations,
# cryptographic keys etc. are subject to a license agreement between
# you and Univention and not subject to the GNU AGPL V3.
#
# In the case you use this program under the terms of the GNU AGPL V3,
# the program is provided in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the
# GNU Affero General Public License for more details.
#
# You should have received a copy of the GNU Affero General Public
# License with the Debian GNU/Linux or Univention distribution in file
# /usr/share/common-licenses/AGPL-3; if not, see
# <http://www.gnu.org/licenses/>.

import datetime
import logging
import multiprocessing
import os
import subprocess
import sys
from typing import Any, Dict, Iterable, Optional

import requests
from faker import Faker
from gevent.lock import BoundedSemaphore
from locust import HttpUser, events

from .auth import SSL_CERT, AuthToken, retrieve_token
from .settings_locust import get_settings
from .test_cleaner import TestCleaner, get_test_cleaner
from .test_data import TestData

logger = logging.getLogger(__name__)


@events.init.add_listener
def on_locust_init(environment, **kwargs):
    if not environment.parsed_options.master:
        return
    environment.worker_processes = []
    master_args = [*sys.argv]
    worker_args = [sys.argv[0]]
    if "-f" in master_args:
        i = master_args.index("-f")
        worker_args += [master_args.pop(i), master_args.pop(i)]
    if "--locustfile" in master_args:
        i = master_args.index("--locustfile")
        worker_args += [master_args.pop(i), master_args.pop(i)]
    worker_args += ["--worker"]
    workers = multiprocessing.cpu_count() - 1
    workers = workers if workers > 0 else 1
    env = {k: v for k, v in os.environ.items() if k != "LOCUST_RUN_TIME"}
    for _ in range(workers):
        logger.info("Starting worker: %r env=%r", worker_args, env)
        p = subprocess.Popen(  # nosec
            worker_args,
            start_new_session=True,
            # LOCUST_RUN_TIME not allowed for workers
            env=env,
        )
        environment.worker_processes.append(p)


@events.quit.add_listener
def clean_test_env(*args, **kwargs):
    get_test_cleaner().delete()


class KelvinClient(HttpUser):
    abstract: bool = True
    auth_token: AuthToken | None = None  # share token with all threads
    token_sem: BoundedSemaphore = BoundedSemaphore()
    fake: Faker = Faker()
    test_data: TestData = TestData()
    test_cleaner: TestCleaner = get_test_cleaner()
    base_path: str = "/ucsschool/kelvin/v1"

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.settings = get_settings()
        self.base_url = f"https://{self.settings.kelvin_host}{self.base_path}"
        self.username = self.settings.kelvin_username
        self.password = self.settings.kelvin_password

    def on_start(self):
        logger.info("Starting client with user %r (ID: %r).", self.username, id(self))
        self.get_token()  # prefetch token

    def request(
        self,
        method: str,
        *args,
        add_auth_token: bool = True,
        headers: Optional[Dict[str, Any]] = None,
        response_codes: Optional[Iterable[int]] = None,
        **kwargs,
    ) -> requests.Response:
        """Wrapper method for HttpUser.client.{method}, adds auth token automatically"""

        headers = headers or {}
        header_keys = {h.lower() for h in headers}
        default_headers = {
            "Accept": "application/json",
            "Accept-Language": "en-US",
            "Content-Type": "application/json",
        }
        for k, v in default_headers.items():
            if k.lower() not in header_keys:
                headers[k] = v
        if add_auth_token:
            headers["Authorization"] = self.get_token()
        assert method in {"delete", "get", "patch", "post", "put", "head"}
        response = getattr(self.client, method)(*args, headers=headers, verify=SSL_CERT, **kwargs)
        if response_codes and response.status_code not in response_codes:
            logger.error(
                (
                    "Request failed for %s %r with status code %r.\n"
                    "method=%r *args=%r add_auth_token=%r headers=%r response_codes=%r kwargs=%r"
                ),
                method.upper(),
                response.url,
                response.status_code,
                method,
                args,
                add_auth_token,
                headers,
                response_codes,
                kwargs,
            )
            logger.error("Response content: %r", response.content)
            if response.status_code == 401:
                with self.token_sem:
                    self.__class__.auth_token = None
        return response

    def get_token(self) -> str:
        with self.token_sem:  # prevent multiple threads fetching a token at the same time
            if not self.__class__.auth_token or self.__class__.auth_token.expired:
                self.__class__.auth_token = retrieve_token(
                    self.settings.kelvin_host, self.username, self.password
                )
                logger.info(
                    "Got new token for %r. Token expires in %d seconds.",
                    self.username,
                    (datetime.datetime.now() - self.__class__.auth_token.expiration_time).seconds,
                )
            return self.__class__.auth_token.token

    def role_url(self, role_name: str) -> str:
        return f"{self.base_url}/roles/{role_name}"

    def school_url(self, school_name: str) -> str:
        return f"{self.base_url}/schools/{school_name}"

    def school_class_url(self, class_name: str) -> str:
        return f"{self.base_url}/classes/{class_name}"

    def user_url(self, user_name: str) -> str:
        return f"{self.base_url}/users/{user_name}"
