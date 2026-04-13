# SPDX-FileCopyrightText: 2026 Univention GmbH
# SPDX-License-Identifier: AGPL-3.0-only

from udm_rest_client import UDM, ModifyError, UdmObject

from .attributes import EmptyAttributes
from .base import UCSSchoolHelperAbstractClass, UCSSchoolModel
from .utils import _


class Policy(UCSSchoolHelperAbstractClass):
    @classmethod
    def get_container(cls, school: str) -> str:
        return cls.get_search_base(school).policies

    async def attach(self, obj: UCSSchoolModel, lo: UDM) -> None:
        # add the missing policy
        udm_obj: UdmObject = await obj.get_udm_object(lo)
        if self.dn.lower() not in [dn.lower() for dn in udm_obj.policies[self.Meta.udm_module]]:
            udm_obj.policies[self.Meta.udm_module].append(self.dn)
        else:
            self.logger.info("Already attached!")
            return
        self.logger.info("Attaching %r to %r", self, obj)
        try:
            await udm_obj.save()
        except ModifyError as exc:
            self.logger.warning("Policy %s cannot be referenced to %r: %s", self, obj, exc)


class UMCPolicy(Policy):
    class Meta:
        udm_module = "policies/umc"


class DHCPDNSPolicy(Policy):
    empty_attributes = EmptyAttributes(_("Empty attributes"))

    class Meta:
        udm_module = "policies/dhcp_dns"
