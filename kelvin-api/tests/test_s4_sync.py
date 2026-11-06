# SPDX-FileCopyrightText: 2026 Univention GmbH
# SPDX-License-Identifier: AGPL-3.0-only

import datetime
from collections.abc import Callable
from typing import Any

import pytest
import requests
from conftest import model_json
from s4_sync import (
    SambaEntry,
    get_ldap_user_attr,
    responsible_s4_connector,
    s4_connectors,
    samba_disabled,
    wait_for_s4_sync,
)
from uldap3 import BindError

from ucsschool.kelvin.routers.v1.user import UserModel, userexpiry_to_shadowExpire

pytestmark = pytest.mark.in_container

ACCOUNT_NEVER_EXPIRES = {b"0", b"9223372036854775807"}


@pytest.fixture
async def s4_replicated_school(create_ou_using_python) -> str:
    connectors = s4_connectors()
    if not connectors:
        pytest.skip("No S4 connector in the domain.")
    if None in connectors.values():
        return await create_ou_using_python()
    school_suffix = next(suffix for suffix in connectors.values() if suffix)
    return school_suffix.split(",", 1)[0].split("=", 1)[1]


@pytest.mark.asyncio
async def test_s4_round_trip_keeps_kelvin_values(
    auth_header,
    check_password,
    retry_http_502,
    url_fragment,
    random_user_create_model,
    schedule_delete_user_name_using_udm,
    import_config,
    s4_replicated_school,
):
    """
    Changes made through Kelvin arrive in Samba, and after the S4 connector's next poll cycle OpenLDAP
    and Kelvin still return what Kelvin wrote.
    """
    school = s4_replicated_school
    user = await random_user_create_model(
        school,
        roles=[f"{url_fragment}/roles/teacher"],
        disabled=False,
        school_classes={},
        workgroups={},
    )
    password = user.password
    schedule_delete_user_name_using_udm(user.name)
    response = retry_http_502(
        requests.post,
        f"{url_fragment}/users/",
        headers={"Content-Type": "application/json", **auth_header},
        data=model_json(user),
    )
    assert response.status_code == 201, response.text
    dn = response.json()["dn"]
    assert responsible_s4_connector(dn)

    async def patch_and_sync(data: dict[str, Any], check: Callable[[SambaEntry], bool]) -> UserModel:
        response = retry_http_502(
            requests.patch, f"{url_fragment}/users/{user.name}", headers=auth_header, json=data
        )
        assert response.status_code == 200, response.text
        await wait_for_s4_sync(dn, user.name, check)
        response = retry_http_502(requests.get, f"{url_fragment}/users/{user.name}", headers=auth_header)
        assert response.status_code == 200, response.text
        return UserModel(**response.json())

    await wait_for_s4_sync(dn, user.name, lambda entry: not samba_disabled(entry))
    await check_password(dn, password)

    api_user = await patch_and_sync({"disabled": True}, samba_disabled)
    assert api_user.disabled is True
    assert "D" in get_ldap_user_attr(user.name, "sambaAcctFlags")
    with pytest.raises(BindError):
        await check_password(dn, password)

    api_user = await patch_and_sync({"disabled": False}, lambda entry: not samba_disabled(entry))
    assert api_user.disabled is False
    assert "D" not in get_ldap_user_attr(user.name, "sambaAcctFlags")
    await check_password(dn, password)

    expiration_date = datetime.date.today() + datetime.timedelta(days=365)

    def expires_set(entry: SambaEntry) -> bool:
        return entry["accountExpires"][0] not in ACCOUNT_NEVER_EXPIRES

    api_user = await patch_and_sync({"expiration_date": str(expiration_date)}, expires_set)
    assert api_user.expiration_date == expiration_date
    assert api_user.disabled is False
    assert get_ldap_user_attr(user.name, "shadowExpire") == userexpiry_to_shadowExpire(expiration_date)
