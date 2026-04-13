# SPDX-FileCopyrightText: 2021 - 2026 Univention GmbH
# SPDX-License-Identifier: AGPL-3.0-only

"""
Example hook class that creates/modifies an email address for a school class.

Copy to /usr/share/ucs-school-import/pyhooks to activate it.

*Attention*: Kelvin version using ``async/await``.
"""

from ucsschool.lib.models.group import SchoolClass
from ucsschool.lib.models.hook import Hook
from udm_rest_client import UDM


class MailForSchoolClass(Hook):
    model = SchoolClass
    priority = {
        "post_create": 10,
        "post_modify": 10,
    }

    async def post_create(self, obj: SchoolClass) -> None:
        """
        Create an email address for the new school class.

        :param SchoolClass obj: the SchoolClass instance, that was just created.
        :return: None
        """
        domain_name = await self.domainname(self.udm)
        ml_name = self.name_for_mailinglist(obj, domain_name)
        self.logger.info("Setting email address %r on %r...", ml_name, obj)
        # The SchoolClass object does not have an email attribute, so we'll have to access the underlying
        # UDM object.
        udm_obj = await obj.get_udm_object(self.udm)
        udm_obj.props.mailAddress = ml_name
        await udm_obj.save()

    async def post_modify(self, obj: SchoolClass) -> None:
        """
        Change the email address of an existing school class, if it didn't have an email or was renamed.

        :param SchoolClass obj: the SchoolClass instance, that was just modified.
        :return: None
        """
        udm_obj = await obj.get_udm_object(self.udm)
        domain_name = await self.domainname(self.udm)
        ml_name = self.name_for_mailinglist(obj, domain_name)
        if udm_obj.props.mailAddress != ml_name:  # this also works if it doesn't have an email address
            self.logger.info(
                "Changing the email address of %r from %r to %r...",
                obj,
                udm_obj.props.mailAddress,
                ml_name,
            )
            udm_obj.props.mailAddress = ml_name
            await udm_obj.save()

    @staticmethod
    def name_for_mailinglist(obj: SchoolClass, domain_name: str) -> str:
        return "{}@{}".format(obj.name, domain_name).lower()

    async def domainname(self, udm: UDM) -> str:
        async for mail_domain_udm_obj in udm.get("mail/domain").search():
            return mail_domain_udm_obj.props.name
        else:
            return self.ucr["domainname"]
