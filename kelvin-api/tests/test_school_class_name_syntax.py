# SPDX-FileCopyrightText: 2026 Univention GmbH
# SPDX-License-Identifier: AGPL-3.0-only

import random
import string
from typing import List

import pytest
import requests
from faker import Faker

import ucsschool.kelvin.constants
from ucsschool.kelvin.routers.school_class import SchoolClass
from udm_rest_client import UDM
from udm_rest_client.exceptions import CreateError

must_run_in_container = pytest.mark.skipif(
    not ucsschool.kelvin.constants.CN_ADMIN_PASSWORD_FILE.exists(),
    reason="Must run inside Docker container started by appcenter.",
)
fake = Faker()


def random_names(name_lengths: List[int], chars: str) -> List[str]:
    names = []
    for n in name_lengths:
        names.append("".join(random.choice(chars) for _ in range(n)))
    return names


@pytest.mark.parametrize(
    "name",
    random_names(random.choices(range(1, 33), k=100), f"{string.ascii_lowercase}{string.digits}"),
)
@must_run_in_container
@pytest.mark.asyncio
async def test_schoolclass_module(name: str, udm_kwargs):
    school = fake.unique.user_name()
    async with UDM(**udm_kwargs) as udm:
        await SchoolClass(name=f"{school}-{name}", school=school).validate(udm)


@must_run_in_container
@pytest.mark.asyncio
async def test_check_class_name(
    auth_header, create_ou_using_python, retry_http_502, url_fragment, new_school_class_using_udm
):
    school_name = await create_ou_using_python()

    names = {"1a", "1-a"}
    name_lengths = random.sample(range(1, 33), 3) + [1] * 3
    names.update(set(random_names(name_lengths, string.ascii_lowercase)))
    names.update(set(random_names(name_lengths, string.digits)))
    for name in names:
        try:
            await new_school_class_using_udm(school=school_name, name=name)
        except CreateError:
            # this test only tests get, so we don't care if the sc exists already
            pass

    response = retry_http_502(
        requests.get,
        f"{url_fragment}/classes/",
        headers={"Content-Type": "application/json", **auth_header},
        params={"school": school_name},
    )
    json_resp = response.json()
    assert response.status_code == 200, response.reason
    # make sure all classes were created.
    received = set(r["name"] for r in json_resp if r["name"] in names)
    assert names == received
