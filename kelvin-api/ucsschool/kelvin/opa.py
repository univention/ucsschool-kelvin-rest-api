from typing import Any, Dict

import aiohttp

from ucsschool.importer.models.import_user import ImportUser

from .constants import OPA_URL


class OPAClient:
    """
    Client to access the Open Policy Agaent (OPA).

    * Use py:meth:`instance()` to get a Singleton instance of py:class:`OPAClient`.
    * The user of this class is expected to call py:meth:`shutdown()` on its instance
      to cleanly close any open HTTP session.
    """

    _instance: "OPAClient" = None

    # sensitive attributes which must not be transmitted to OPA
    # as they might be shown in the general or decision logs
    _sensitive_attributes = ["password", "kelvin_password_hashes"]
    _mask_value = "********"

    @classmethod
    def instance(cls):
        if not cls._instance:
            cls._instance = cls()
        return cls._instance

    @classmethod
    async def shutdown_instance(cls):
        if cls._instance:
            await cls._instance.shutdown()

    @classmethod
    def filter_sensitive_attributes(cls, request: Dict[str, Any]) -> Dict[str, Any]:
        for attr in OPAClient._sensitive_attributes:
            if attr in request.get("data", {}):
                request["data"][attr] = OPAClient._mask_value
        return request

    def __init__(self):
        self._session = aiohttp.ClientSession()

    async def shutdown(self):
        await self._session.close()

    async def check_policy(
        self, policy: str, token: str, request: Dict[str, Any], target: Dict[str, Any]
    ) -> Any:
        async with self._session.post(
            f"{OPA_URL}{policy}",
            json={
                "input": {
                    "token": token,
                    "request": OPAClient.filter_sensitive_attributes(request),
                    "target": target,
                }
            },
        ) as response:
            if response.status != 200:
                return False
            return (await response.json()).get("result", False)

    async def check_policy_true(
        self, policy: str, token: str, request: Dict[str, Any], target: Dict[str, Any]
    ) -> bool:
        response_data = await self.check_policy(policy, token, request, target)
        return response_data is True


def import_user_to_opa(user: ImportUser) -> Dict[str, Any]:
    return {
        "username": user.name,
        "schools": user.schools,
        "roles": user.ucsschool_roles,
    }
