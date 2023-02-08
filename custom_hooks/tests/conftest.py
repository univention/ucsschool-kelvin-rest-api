import json
import random
import string

import pytest
import requests

from univention.config_registry import ConfigRegistry

ucr = ConfigRegistry()
ucr.load()


@pytest.fixture
def random_name():
    """To create unique user names."""

    def _wrapper():
        return "".join(random.choice(string.ascii_lowercase + string.digits) for _ in range(5))  # nosec

    return _wrapper


@pytest.fixture
def get_base():
    return ucr["ldap/base"]


@pytest.fixture
def get_fqdn():
    return ucr["interfaces/eth0/address"]


@pytest.fixture
def get_login():
    return {"username": "Administrator", "password": "univention"}


@pytest.fixture
def kelvin_token(kelvin_auth):
    return json.loads(kelvin_auth.text)["access_token"]


@pytest.fixture
def kelvin_auth(get_fqdn, get_login):
    return requests.post(
        "http://%s/ucsschool/kelvin/token" % get_fqdn,
        headers={"Content-Type": "application/x-www-form-urlencoded"},
        data=get_login,
    )


@pytest.fixture
def kelvin_create_user_with_role(get_fqdn, kelvin_token, random_name):
    async def _wrapper(role):
        tmpname = random_name()
        payload = {
            "name": tmpname,
            "password": "univention",
            "firstname": random_name(),
            "lastname": random_name(),
            "school": "https://%s/ucsschool/kelvin/v1/schools/DEMOSCHOOL" % get_fqdn,
            "schools": ["https://%s/ucsschool/kelvin/v1/schools/DEMOSCHOOL" % get_fqdn],
            "record_uid": tmpname,
            "roles": ["https://%s/ucsschool/kelvin/v1/roles/staff" % get_fqdn],
            "ucsschool_roles": [role],
        }
        return requests.post(
            "http://%s/ucsschool/kelvin/v1/users/" % get_fqdn,
            headers={
                "accept": "application/json",
                "Content-Type": "application/json",
                "Authorization": "Bearer %s" % kelvin_token,
            },
            data=json.dumps(payload),
        )

    return _wrapper
