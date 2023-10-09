import pytest
import requests


@pytest.mark.parametrize("ip_first", [True, False], ids=["ip_first", "ip_last"])
@pytest.mark.asyncio
async def test_url_caching(
    set_processes_to_one,
    url_fragment,
    url_fragment_ip,
    retry_http_502,
    auth_header,
    create_ou_using_python,
    random_user_create_model,
    ip_first,
):
    """Caching URLs can lead to problems when comparing resources

    - This test ensures that it does not matter whether a user is created with either IP or FQDN.
    - To ensure we hit the same worker process and cache,
      we set the number of processes for this test to 1
    - See Bug #56699
    """
    school = await create_ou_using_python()

    roles = ["student"]

    if ip_first:
        order = [url_fragment_ip, url_fragment]
    else:
        order = [url_fragment, url_fragment_ip]
    for url in order:
        r_user = await random_user_create_model(
            school,
            roles=[f"{url}/roles/{role_}" for role_ in roles],
        )
        response = retry_http_502(
            requests.post,
            f"{url}/users/",
            headers={"Content-Type": "application/json", **auth_header},
            data=r_user.json(),
        )
        assert response.status_code == 201, response.reason
