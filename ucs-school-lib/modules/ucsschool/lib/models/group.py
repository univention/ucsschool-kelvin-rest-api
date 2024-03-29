# -*- coding: utf-8 -*-
#
# UCS@school python lib: models
#
# Copyright 2014-2021 Univention GmbH
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

from typing import Any, AsyncIterator, Dict, List, Optional, Type

from ldap.dn import str2dn

from udm_rest_client import UDM, NoObject as UdmNoObject, UdmObject

from ..roles import (
    create_ucsschool_role_string,
    role_computer_room,
    role_computer_room_backend_veyon,
    role_school_class,
    role_workgroup,
)
from .attributes import Attribute, Description, Email, GroupName, Groups, Hosts, SchoolClassName, Users
from .base import PYHOOKS_BASE_CLASS  # noqa: F401
from .base import RoleSupportMixin, UCSSchoolHelperAbstractClass, UCSSchoolModel
from .misc import OU, Container
from .policy import UMCPolicy
from .share import ClassShare, WorkGroupShare
from .utils import _, ucr, uldap_exists


class _MayHaveSchoolPrefix(object):
    def get_relative_name(self) -> str:
        # schoolname-1a => 1a
        if self.school and self.name.lower().startswith("%s-" % self.school.lower()):
            return self.name[len(self.school) + 1 :]
        return self.name

    def get_replaced_name(self, school: str) -> str:
        if self.name != self.get_relative_name():
            return "%s-%s" % (school, self.get_relative_name())
        return self.name


class _MayHaveSchoolSuffix(object):
    def get_relative_name(self) -> str:
        # schoolname-1a => 1a
        if (
            self.school
            and self.name.lower().endswith("-%s" % self.school.lower())
            or self.name.lower().endswith(" %s" % self.school.lower())
        ):
            return self.name[: -(len(self.school) + 1)]
        return self.name

    def get_replaced_name(self, school: str) -> str:
        if self.name != self.get_relative_name():
            delim = self.name[len(self.get_relative_name())]
            return "%s%s%s" % (self.get_relative_name(), delim, school)
        return self.name


class EmailAttributesMixin(object):
    email: str = Email(
        _("Email"), udm_name="mailAddress", aka=["Email", "E-Mail"], unlikely_to_change=True
    )
    allowed_email_senders_users: List[str] = Users(
        _("Users that are allowed to send e-mails to the group"), udm_name="allowedEmailUsers"
    )
    allowed_email_senders_groups: List[str] = Groups(
        _("Groups that are allowed to send e-mails to the group"), udm_name="allowedEmailGroups"
    )


class Group(RoleSupportMixin, UCSSchoolHelperAbstractClass):
    name: str = GroupName(_("Name"))
    description: str = Description(_("Description"))
    users: List[str] = Users(_("Users"))

    @classmethod
    def get_container(cls, school: str) -> str:
        return cls.get_search_base(school).groups

    @classmethod
    def is_school_group(cls, school: str, group_dn: str) -> bool:
        return cls.get_search_base(school).isGroup(group_dn)

    @classmethod
    def is_school_workgroup(cls, school: str, group_dn: str) -> bool:
        return cls.get_search_base(school).isWorkgroup(group_dn)

    @classmethod
    def is_school_class(cls, school: str, group_dn: str) -> bool:
        return cls.get_search_base(school).isClass(group_dn)

    @classmethod
    def is_computer_room(cls, school: str, group_dn: str) -> bool:
        return cls.get_search_base(school).isRoom(group_dn)

    def self_is_workgroup(self) -> bool:
        return self.is_school_workgroup(self.school, self.dn)

    def self_is_class(self) -> bool:
        return self.is_school_class(self.school, self.dn)

    def self_is_computerroom(self) -> bool:
        return self.is_computer_room(self.school, self.dn)

    @classmethod
    async def get_class_for_udm_obj(cls, udm_obj: UdmObject, school: str) -> Type["Group"]:
        if cls.is_school_class(school, udm_obj.dn):
            return SchoolClass
        elif cls.is_computer_room(school, udm_obj.dn):
            return ComputerRoom
        elif cls.is_school_workgroup(school, udm_obj.dn):
            return WorkGroup
        elif cls.is_school_group(school, udm_obj.dn):
            return SchoolGroup
        return cls

    async def add_umc_policy(self, policy_dn: str, lo: UDM) -> None:
        if not policy_dn or policy_dn.lower() == "none":
            self.logger.warning("No policy added to %r", self)
            return
        try:
            policy = await UMCPolicy.from_dn(policy_dn, self.school, lo)
        except UdmNoObject:
            self.logger.warning(
                "Object to be referenced does not exist (or is no UMC-Policy): %s", policy_dn
            )
        else:
            await policy.attach(self, lo)

    class Meta:
        udm_module = "groups/group"
        name_is_unique = True
        _ldap_filter = f"(&(univentionObjectType={udm_module})(cn={{name}}))"


class BasicGroup(Group):
    school: str = None
    container: str = Attribute(_("Container"), required=True)

    def __init__(self, name: str = None, school: str = None, **kwargs):
        if "container" not in kwargs:
            kwargs["container"] = "cn=groups,%s" % ucr.get("ldap/base")
        super(BasicGroup, self).__init__(name=name, school=school, **kwargs)

    async def create_without_hooks(self, lo: UDM, validate: bool) -> bool:
        # prepare LDAP: create containers where this basic group lives if necessary
        # Does not work correctly for non-school groups: they will be created at the LDAPs root!
        # -> Create containers for non-school group manually before creating the group.
        if not await self.container_exists(lo):
            await self.create_groups_container(lo)
        return await super(BasicGroup, self).create_without_hooks(lo, validate)

    async def create_groups_container(self, lo: UDM) -> None:
        container_dn = self.get_own_container()[: -len(ucr.get("ldap/base")) - 1]
        containers = str2dn(container_dn)
        super_container_dn = ucr.get("ldap/base")
        for container_info in reversed(containers):
            dn_part, cn = container_info[0][0:2]
            if dn_part.lower() == "ou":
                container = OU(name=cn)
            else:
                container = Container(name=cn, school="", group_path="1")
            container.position = super_container_dn
            if not await container.exists(lo):
                await container.create(lo, False)

    def get_own_container(self) -> Optional[str]:
        return self.container

    async def container_exists(self, lo: UDM) -> bool:
        filter_s, base = self.get_own_container().split(",", 1)
        return uldap_exists(f"(&(univentionObjectType=container/cn)({filter_s}))", search_base=base)

    def build_hook_line(self, hook_time: str, func_name: str) -> Optional[str]:
        return None

    @classmethod
    def get_container(cls, school: str = None) -> str:
        return ucr.get("ldap/base")

    def update_ucsschool_roles(self) -> None:
        # Bug 55986: BasicGroup doesn't have a school,
        # which means that all school roles get removed from this object when saving
        # (see models.base.RoleSupportMixin).
        # However, some administrative groups get the `school_admin_group` role,
        # which should not be removed.
        # If a BasicGroup has a role, don't remove it.
        # We don't update these after creation, so the roles should be correct.
        pass

    async def validate_roles(self, lo: UDM) -> None:
        # Bug 55986: Related to update_ucsschool_roles fix above.
        # If we keep the `school_admin_group` role when updating,
        # the RoleSupportMixin complains that this BasicGroup
        # is not in the school where the role is present, based on the OU.
        # However, BasicGroups are not in the school OU;
        # the role is correct, and we want to allow it regardless.
        # We may want to create some better validation when we redo this library;
        # for now we'll just allow it.
        # We don't update these after creation, so the roles should be correct.
        pass


class BasicSchoolGroup(BasicGroup):
    school: str = Group.school


class SchoolGroup(Group, _MayHaveSchoolSuffix):
    pass


class SchoolClass(Group, _MayHaveSchoolPrefix):
    name: str = SchoolClassName(_("Name"))

    default_roles: List[str] = [role_school_class]
    _school_in_name_prefix = True
    ShareClass = ClassShare

    def __init__(
        self, name: str = None, school: str = None, create_share: bool = True, **kwargs
    ) -> None:
        super(SchoolClass, self).__init__(name, school, **kwargs)
        self._create_share = create_share

    async def create_without_hooks(self, lo: UDM, validate: bool) -> bool:
        success = await super(SchoolClass, self).create_without_hooks(lo, validate)
        if self._create_share and await self.exists(lo):
            success = success and await self.create_share(lo)
        return success

    async def create_share(self, lo: UDM) -> bool:
        share = self.ShareClass.from_school_group(self)
        if not (res := await share.exists(lo)):
            self.logger.info("Creating %r (for %r)...", share, self)
            res = await share.create(lo)
        return res

    async def modify_without_hooks(
        self, lo: UDM, validate: bool = True, move_if_necessary: bool = None
    ) -> bool:
        share = self.ShareClass.from_school_group(self)
        if self.old_dn:
            old_name = self.get_name_from_dn(self.old_dn)
            if old_name != self.name:
                # recreate the share.
                # if the name changed
                # from_school_group will have initialized
                # share.old_dn incorrectly
                share = self.ShareClass(name=old_name, school=self.school, school_group=self)
                share.name = self.name
        success = await super(SchoolClass, self).modify_without_hooks(lo, validate, move_if_necessary)
        if success and await share.exists(lo):
            self.logger.info("Modifying %r (of %r)...", share, self)
            success = success and await share.modify(lo)
        return success

    async def remove_without_hooks(self, lo: UDM) -> bool:
        success = await super(SchoolClass, self).remove_without_hooks(lo)
        if success:
            share = self.ShareClass.from_school_group(self)
            if await share.exists(lo):
                self.logger.info("Removing %r (of %r)...", share, self)
                success = success and await share.remove(lo)
        return success

    @classmethod
    def get_container(cls, school: str) -> str:
        return cls.get_search_base(school).classes

    def to_dict(self) -> Dict[str, Any]:
        ret = super(SchoolClass, self).to_dict()
        ret["name"] = self.get_relative_name()
        return ret

    @classmethod
    async def get_class_for_udm_obj(
        cls, udm_obj: UdmObject, school: str
    ) -> Optional[Type["SchoolClass"]]:
        if not cls.is_school_class(school, udm_obj.dn):
            return  # is a workgroup
        return cls

    @classmethod
    def hook_init(cls, hook):  # type: (PYHOOKS_BASE_CLASS) -> None
        """
        Add method :py:func:`get_share` to SchoolClass hooks, to make the
        associated share easily accessible in hooks.

        :param hook: instance of a subclass of :py:class:`ucsschool.lib.model.hook.Hook`
        :return: None
        :rtype: None
        """

        def get_share(grp):
            share = cls.ShareClass.from_school_group(grp)
            if not share.school_group:
                # fix empty attr
                # TODO: investigate if this should be generally fixed
                share.school_group = grp
            return share

        hook.get_share = get_share

    async def validate(self, lo: UDM, validate_unlikely_changes: bool = False) -> None:
        await super(SchoolClass, self).validate(lo, validate_unlikely_changes)
        if not self.name.startswith("{}-".format(self.school)):
            raise ValueError("Missing school prefix in name: {!r}.".format(self))

    class Meta:
        udm_module = "groups/group"
        name_is_unique = True
        udm_filter = f"(&(univentionObjectType={udm_module})(ucsschoolRole=school_class:school:*))"
        _ldap_filter = (
            f"(&(univentionObjectType={udm_module})(ucsschoolRole=school_class:school*)(cn={{name}}))"
        )


class WorkGroup(EmailAttributesMixin, SchoolClass, _MayHaveSchoolPrefix):
    default_roles: List[str] = [role_workgroup]
    ShareClass = WorkGroupShare

    @classmethod
    def get_container(cls, school: str) -> str:
        return cls.get_search_base(school).workgroups

    @classmethod
    async def get_class_for_udm_obj(cls, udm_obj: UdmObject, school: str) -> Optional[Type["WorkGroup"]]:
        if not cls.is_school_workgroup(school, udm_obj.dn):
            return
        return cls

    class Meta:
        udm_module = "groups/group"
        name_is_unique = True
        udm_filter = f"(&(univentionObjectType={udm_module})(ucsschoolRole=workgroup:school:*))"
        _ldap_filter = (
            f"(&(univentionObjectType={udm_module})(ucsschoolRole=workgroup:school*)(cn={{name}}))"
        )


class ComputerRoom(Group, _MayHaveSchoolPrefix):
    hosts: List[str] = Hosts(_("Hosts"))

    users: List[UCSSchoolModel] = None
    default_roles: List[str] = [role_computer_room]

    def to_dict(self) -> Dict[str, Any]:
        ret = super(ComputerRoom, self).to_dict()
        ret["name"] = self.get_relative_name()
        return ret

    @classmethod
    def get_container(cls, school: str) -> str:
        return cls.get_search_base(school).rooms

    @property
    def veyon_backend(self) -> bool:
        """True if the computerroom is configured to use the new veyon backend instead of italc."""
        return (
            create_ucsschool_role_string(role_computer_room_backend_veyon, "-") in self.ucsschool_roles
        )

    @veyon_backend.setter
    def veyon_backend(self, is_veyon_backend):
        role_string = create_ucsschool_role_string(role_computer_room_backend_veyon, "-")
        if not is_veyon_backend and self.veyon_backend:
            self.ucsschool_roles.remove(role_string)
        if is_veyon_backend and not self.veyon_backend:
            self.ucsschool_roles.append(role_string)

    async def get_computers(self, ldap_connection: UDM) -> AsyncIterator[UCSSchoolModel]:
        from ucsschool.lib.models.computer import SchoolComputer

        for host in self.hosts:
            try:
                yield await SchoolComputer.from_dn(host, self.school, ldap_connection)
            except UdmNoObject:
                continue

    def get_schools_from_udm_obj(self, udm_obj: UdmObject) -> str:
        # fixme: no idea how to find out old school
        return self.school
