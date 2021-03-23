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
from __future__ import annotations

from typing import Any, Dict, List, Optional, Type

import six
from ipaddr import AddressValueError, IPv4Network, NetmaskValueError
from ldap.filter import escape_filter_chars

from udm_rest_client import UDM, UdmObject
from univention.admin.filter import conjunction, expression, parse
from univention.admin.uexceptions import nextFreeIp

from ..roles import (
    create_ucsschool_role_string,
    role_ip_computer,
    role_mac_computer,
    role_teacher_computer,
    role_win_computer,
)
from .attributes import Attribute, Groups, InventoryNumber, IPAddress, MACAddress, SubnetMask
from .base import MultipleObjectsError, RoleSupportMixin, SuperOrdinateType, UCSSchoolHelperAbstractClass
from .dhcp import AnyDHCPService, DHCPServer
from .group import BasicGroup
from .network import Network
from .utils import _, ucr


class AnyComputer(UCSSchoolHelperAbstractClass):
    @classmethod
    def get_container(cls, school: str = None) -> str:
        from ucsschool.lib.models.school import School

        if school:
            return School.cache(school).dn
        return ucr.get("ldap/base")

    class Meta:
        udm_module = "computers/computer"


class SchoolDC(UCSSchoolHelperAbstractClass):
    # NOTE: evaluate filter (&(service=UCS@school)(service=UCS@school Education))
    # UCS@school Administration vs. group memberships

    @classmethod
    def get_container(cls, school: str) -> str:
        return "cn=dc,cn=server,%s" % cls.get_search_base(school).computers

    @classmethod
    async def get_class_for_udm_obj(cls, udm_obj: UdmObject, school: str) -> Optional[Type["SchoolDC"]]:
        module_to_class = {
            SchoolDCSlave.Meta.udm_module: SchoolDCSlave,
        }
        return module_to_class.get(udm_obj._udm_module.name, cls)


class SchoolDCSlave(RoleSupportMixin, SchoolDC):
    groups: List[str] = Groups(_("Groups"))

    async def do_create(self, udm_obj: UdmObject, lo: UDM) -> None:
        udm_obj.props.unixhome = "/dev/null"
        udm_obj.props.shell = "/bin/bash"
        udm_obj.props.primaryGroup = BasicGroup.cache("DC Slave Hosts").dn
        return await super(SchoolDCSlave, self).do_create(udm_obj, lo)

    async def _alter_udm_obj(self, udm_obj: UdmObject) -> None:
        if self.groups:
            for group in self.groups:
                if group not in udm_obj.props.groups:
                    udm_obj.props.groups.append(group)
        return await super(SchoolDCSlave, self)._alter_udm_obj(udm_obj)

    async def get_schools_from_udm_obj(self, udm_obj: UdmObject) -> str:
        # fixme: no idea how to find out old school
        return self.school

    async def move_without_hooks(self, lo: UDM, udm_obj: UdmObject = None, force: bool = False) -> bool:
        try:
            if udm_obj is None:
                try:
                    udm_obj = await self.get_only_udm_obj(lo, "cn=%s" % escape_filter_chars(self.name))
                except MultipleObjectsError:
                    self.logger.error('Found more than one DC Slave with hostname "%s"', self.name)
                    return False
                if udm_obj is None:
                    self.logger.error('Cannot find DC Slave with hostname "%s"', self.name)
                    return False
            old_dn = udm_obj.dn
            school = await self.get_school_obj(lo)
            group_dn = school.get_administrative_group_name("educational", ou_specific=True, as_dn=True)
            if group_dn not in udm_obj.props.groups:
                self.logger.error("%r has no LDAP access to %r", self, school)
                return False
            if old_dn == self.dn:
                self.logger.info(
                    'DC Slave "%s" is already located in "%s" - stopping here', self.name, self.school
                )
            self.set_dn(old_dn)
            if await self.exists_outside_school(lo):
                if not force:
                    self.logger.error(
                        'DC Slave "%s" is located in another OU - %s', self.name, udm_obj.dn
                    )
                    self.logger.error("Use force=True to override")
                    return False
            if school is None:
                self.logger.error("Cannot move DC Slave object - School does not exist: %r", school)
                return False
            await self.modify_without_hooks(lo)
            if school.class_share_file_server == old_dn:
                school.class_share_file_server = self.dn
            if school.home_share_file_server == old_dn:
                school.home_share_file_server = self.dn
            await school.modify_without_hooks(lo)

            removed = False
            # find dhcp server object by checking all dhcp service objects
            for dhcp_service in await AnyDHCPService.get_all(lo, None):
                for dhcp_server in await dhcp_service.get_servers(lo):
                    if dhcp_server.name == self.name and not dhcp_server.dn.endswith(",%s" % school.dn):
                        await dhcp_server.remove(lo)
                        removed = True

            if removed:
                own_dhcp_service = school.get_dhcp_service()

                dhcp_server = DHCPServer(
                    name=self.name, school=self.school, dhcp_service=own_dhcp_service
                )
                await dhcp_server.create(lo)

            self.logger.info("Move complete")
            self.logger.warning("The DC Slave has to be rejoined into the domain!")
        finally:
            self.invalidate_cache()
        return True

    class Meta:
        udm_module = "computers/domaincontroller_slave"
        name_is_unique = True
        allow_school_change = True


class SchoolComputer(UCSSchoolHelperAbstractClass):
    ip_address: List[str] = IPAddress(_("IP address"), required=True)
    subnet_mask: str = SubnetMask(_("Subnet mask"))
    mac_address: List[str] = MACAddress(_("MAC address"), required=True)
    inventory_number: str = InventoryNumber(_("Inventory number"))
    zone: str = Attribute(_("Zone"))

    type_name = _("Computer")

    DEFAULT_PREFIX_LEN = 24  # 255.255.255.0

    @classmethod
    async def lookup(
        cls, lo: UDM, school: str, filter_s: str = "", superordinate: SuperOrdinateType = None
    ) -> List[UdmObject]:
        """
        This override limits the returned objects to actual ucsschoolComputers. Does not contain
        SchoolDC slaves and others anymore.
        """
        object_class_filter = expression("objectClass", "ucsschoolComputer", "=")
        if filter_s:
            school_computer_filter = conjunction("&", [object_class_filter, parse(filter_s)])
        else:
            school_computer_filter = object_class_filter
        return await super(SchoolComputer, cls).lookup(lo, school, school_computer_filter, superordinate)

    def get_inventory_numbers(self) -> List[str]:
        if isinstance(self.inventory_number, six.string_types):
            return [inv.strip() for inv in self.inventory_number.split(",")]
        if isinstance(self.inventory_number, (list, tuple)):
            return list(self.inventory_number)
        return []

    @property
    def teacher_computer(self) -> bool:
        """True if the computer is a teachers computer."""
        return create_ucsschool_role_string(role_teacher_computer, self.school) in self.ucsschool_roles

    @teacher_computer.setter
    def teacher_computer(self, new_value: bool) -> None:
        """Un/mark computer as a teachers computer."""
        role_str = create_ucsschool_role_string(role_teacher_computer, self.school)
        if new_value and role_str not in self.ucsschool_roles:
            self.ucsschool_roles.append(role_str)
        elif not new_value and role_str in self.ucsschool_roles:
            self.ucsschool_roles.remove(role_str)

    async def _alter_udm_obj(self, udm_obj: UdmObject) -> None:
        await super(SchoolComputer, self)._alter_udm_obj(udm_obj)
        inventory_numbers = self.get_inventory_numbers()
        if inventory_numbers:
            udm_obj.props.inventoryNumber = inventory_numbers
        ipv4_network = self.get_ipv4_network()
        if ipv4_network and len(udm_obj.props.ip) < 2:
            if self._ip_is_set_to_subnet(ipv4_network):
                self.logger.info(
                    "IP was set to subnet. Unsetting it on the computer so that UDM can do some magic: "
                    "Assign next free IP!"
                )
                udm_obj.props.ip = []
            else:
                udm_obj.props.ip = [str(ipv4_network.ip)]
            # set network after ip. Otherwise UDM does not do any
            #   nextIp magic...
            network = self.get_network()
            if network:
                # reset network, so that next line triggers free ip
                udm_obj.old_network = None
                try:
                    udm_obj.props.network = network.dn
                except nextFreeIp:
                    self.logger.error("Tried to set IP automatically, but failed! %r is full", network)
                    raise nextFreeIp(_("There are no free addresses left in the subnet!"))

    @classmethod
    def get_container(cls, school: str) -> str:
        return cls.get_search_base(school).computers

    async def create(self, lo: UDM, validate: bool = True) -> bool:
        if self.subnet_mask is None:
            self.subnet_mask = self.DEFAULT_PREFIX_LEN
        return await super(SchoolComputer, self).create(lo, validate)

    async def create_without_hooks(self, lo: UDM, validate: bool) -> bool:
        await self.create_network(lo)
        return await super(SchoolComputer, self).create_without_hooks(lo, validate)

    async def modify_without_hooks(
        self, lo: UDM, validate: bool = True, move_if_necessary: bool = None
    ) -> bool:
        await self.create_network(lo)
        return await super(SchoolComputer, self).modify_without_hooks(lo, validate, move_if_necessary)

    def get_ipv4_network(self) -> IPv4Network:
        if self.subnet_mask is not None and len(self.ip_address) > 0:
            network_str = "%s/%s" % (self.ip_address[0], self.subnet_mask)
        elif len(self.ip_address) > 0:
            network_str = str(self.ip_address[0])
        else:
            network_str = ""
        try:
            return IPv4Network(network_str)
        except (AddressValueError, NetmaskValueError, ValueError):
            self.logger.warning("Unparsable network: %r", network_str)

    def _ip_is_set_to_subnet(self, ipv4_network: IPv4Network = None) -> bool:
        ipv4_network = ipv4_network or self.get_ipv4_network()
        if ipv4_network:
            return ipv4_network.ip == ipv4_network.network

    def get_network(self) -> Network:
        ipv4_network = self.get_ipv4_network()
        if ipv4_network:
            network_name = "%s-%s" % (self.school.lower(), ipv4_network.network)
            network = str(ipv4_network.network)
            netmask = str(ipv4_network.netmask)
            broadcast = str(ipv4_network.broadcast)
            return Network.cache(
                network_name, self.school, network=network, netmask=netmask, broadcast=broadcast
            )

    async def create_network(self, lo: UDM) -> Network:
        network = self.get_network()
        if network:
            await network.create(lo)
        return network

    async def validate(self, lo: UDM, validate_unlikely_changes: bool = False) -> None:
        await super(SchoolComputer, self).validate(lo, validate_unlikely_changes)
        for ip_address in self.ip_address:
            name, ip_address = escape_filter_chars(self.name), escape_filter_chars(ip_address)
            if await AnyComputer.get_first_udm_obj(lo, "&(!(cn=%s))(ip=%s)" % (name, ip_address)):
                self.add_error(
                    "ip_address",
                    _(
                        "The ip address is already taken by another computer. Please change the ip "
                        "address."
                    ),
                )
        for mac_address in self.mac_address:
            name, mac_address = escape_filter_chars(self.name), escape_filter_chars(mac_address)
            if await AnyComputer.get_first_udm_obj(lo, "&(!(cn=%s))(mac=%s)" % (name, mac_address)):
                self.add_error(
                    "mac_address",
                    _(
                        "The mac address is already taken by another computer. Please change the mac "
                        "address."
                    ),
                )
        own_network = self.get_network()
        own_network_ip4 = self.get_ipv4_network()
        if own_network and not await own_network.exists(lo):
            self.add_warning(
                "subnet_mask",
                _(
                    "The specified IP and subnet mask will cause the creation of a new network during "
                    "the creation of the computer object."
                ),
            )
            mod = lo.get("networks/network")
            networks = [
                (
                    network.props.name,
                    IPv4Network(network.props.network + "/" + network.props.netmask),
                )
                async for network in mod.search()
            ]
            is_singlemaster = ucr.get("ucsschool/singlemaster", False)
            for network in networks:
                if is_singlemaster and network[0] == "default" and own_network_ip4 == network[1]:
                    # Bug #48099: jump conflict with default network in singleserver environment
                    continue
                if own_network_ip4.overlaps(network[1]):
                    self.add_error(
                        "subnet_mask",
                        _("The newly created network would overlap with the existing network {}").format(
                            network[0]
                        ),
                    )

    @classmethod
    async def get_class_for_udm_obj(
        cls, udm_obj: UdmObject, school: str
    ) -> Optional[Type["SchoolComputer"]]:
        module_to_class = {
            IPComputer.Meta.udm_module: IPComputer,
            MacComputer.Meta.udm_module: MacComputer,
            UCCComputer.Meta.udm_module: UCCComputer,
            WindowsComputer.Meta.udm_module: WindowsComputer,
        }
        return module_to_class.get(udm_obj._udm_module.name)

    @classmethod
    async def from_udm_obj(cls, udm_obj: UdmObject, school: str, lo: UDM) -> "SchoolComputer":
        from ucsschool.lib.models.school import School

        obj = await super(SchoolComputer, cls).from_udm_obj(udm_obj, school, lo)
        obj.ip_address = udm_obj.props.ip
        school_obj: School = School.cache(obj.school)
        edukativnetz_group = school_obj.get_administrative_group_name(
            "educational", domain_controller=False, as_dn=True
        )
        if edukativnetz_group in udm_obj.props.groups:
            obj.zone = "edukativ"
        verwaltungsnetz_group = school_obj.get_administrative_group_name(
            "administrative", domain_controller=False, as_dn=True
        )
        if verwaltungsnetz_group in udm_obj.props.groups:
            obj.zone = "verwaltung"
        network_dn = udm_obj.props.network
        if network_dn:
            netmask = await Network.get_netmask(network_dn, school, lo)
            obj.subnet_mask = netmask
        obj.inventory_number = ", ".join(udm_obj.props.inventoryNumber)
        return obj

    def to_dict(self) -> Dict[str, Any]:
        ret = super(SchoolComputer, self).to_dict()
        ret["type_name"] = self.type_name
        ret["type"] = self._meta.udm_module_short
        return ret

    class Meta:
        udm_module = "computers/computer"
        name_is_unique = True


class WindowsComputer(RoleSupportMixin, SchoolComputer):
    type_name = _("Windows system")
    default_roles = [role_win_computer]

    class Meta(SchoolComputer.Meta):
        udm_module = "computers/windows"


class MacComputer(RoleSupportMixin, SchoolComputer):
    type_name = _("Mac OS X")
    default_roles = [role_mac_computer]

    class Meta(SchoolComputer.Meta):
        udm_module = "computers/macos"


class IPComputer(RoleSupportMixin, SchoolComputer):
    type_name = _("Device with IP address")
    default_roles = [role_ip_computer]

    class Meta(SchoolComputer.Meta):
        udm_module = "computers/ipmanagedclient"


class UCCComputer(SchoolComputer):
    type_name = _("Univention Corporate Client")

    class Meta(SchoolComputer.Meta):
        udm_module = "computers/ucc"
