# SPDX-FileCopyrightText: 2026 Univention GmbH
# SPDX-License-Identifier: AGPL-3.0-only

from typing import Dict, Optional

from ipaddr import AddressValueError, IPv4Network, NetmaskValueError

from udm_rest_client import UDM, UdmObject
from univention.admin.uexceptions import noObject

from .attributes import Netmask, NetworkAttribute, NetworkBroadcastAddress, SubnetName
from .base import UCSSchoolHelperAbstractClass
from .dhcp import DHCPSubnet
from .utils import _, ucr


class Network(UCSSchoolHelperAbstractClass):
    netmask: str = Netmask(_("Netmask"))
    network: str = NetworkAttribute(_("Network"))
    broadcast: str = NetworkBroadcastAddress(_("Broadcast"))

    _netmask_cache: Dict[str, str] = {}

    @classmethod
    def get_container(cls, school: str) -> str:
        return cls.get_search_base(school).networks

    def get_subnet(self) -> str:
        # WORKAROUND for Bug #14795
        subnetbytes = 0
        netmask_parts = self.netmask.split(".")
        for part in netmask_parts:
            if part == "255":
                subnetbytes += 1
            else:
                break
        return ".".join(self.network.split(".")[:subnetbytes])

    async def create_without_hooks(self, lo: UDM, validate: bool) -> bool:
        dns_reverse_zone = DNSReverseZone.cache(self.get_subnet())
        await dns_reverse_zone.create(lo)

        dhcp_service = (await self.get_school_obj(lo)).get_dhcp_service()
        dhcp_subnet = DHCPSubnet(
            name=self.network,
            school=self.school,
            subnet_mask=self.netmask,
            broadcast=self.broadcast,
            dhcp_service=dhcp_service,
        )
        await dhcp_subnet.create(lo)

        # TODO:
        # set netbios and router for dhcp subnet
        # if defaultrouter:
        # 	print 'setting default router'
        # 	set_router_for_subnet (network, defaultrouter, schoolNr)

        # if netbiosserver:
        # 	print 'setting netbios server'
        # 	set_netbiosserver_for_subnet (network, netbiosserver, schoolNr)

        # set default value for nameserver
        # if nameserver:
        # 	print 'setting nameserver'
        # 	set_nameserver_for_subnet (network, nameserver, schoolNr)

        return await super(Network, self).create_without_hooks(lo, validate)

    async def do_create(self, udm_obj: UdmObject, lo: UDM) -> None:
        from ucsschool.lib.models.school import School

        # TODO:
        # if iprange:
        # 	object['ipRange']=[[str(iprange[0]), str(iprange[1])]]
        # TODO: this is a DHCPServer created when school is created (not implemented yet)
        udm_obj.props.dhcpEntryZone = "cn=%s,cn=dhcp,%s" % (self.school, School.cache(self.school).dn)
        udm_obj.props.dnsEntryZoneForward = "zoneName=%s,cn=dns,%s" % (
            ucr.get("domainname"),
            ucr.get("ldap/base"),
        )
        reversed_subnet = ".".join(reversed(self.get_subnet().split(".")))
        udm_obj.props.dnsEntryZoneReverse = "zoneName=%s.in-addr.arpa,cn=dns,%s" % (
            reversed_subnet,
            ucr.get("ldap/base"),
        )
        return await super(Network, self).do_create(udm_obj, lo)

    @classmethod
    def invalidate_cache(cls) -> None:
        super(Network, cls).invalidate_cache()
        cls._netmask_cache.clear()

    @classmethod
    async def get_netmask(cls, dn: str, school: str, lo: UDM) -> Optional[str]:
        if dn not in cls._netmask_cache:
            try:
                network = await cls.from_dn(dn, school, lo)
            except noObject:
                return
            netmask: str = network.netmask  # e.g. '24'
            network_str = "0.0.0.0/%s" % netmask
            try:
                ipv4_network = IPv4Network(network_str)
            except (AddressValueError, NetmaskValueError, ValueError):
                cls.logger.warning("Unparsable network: %r", network_str)
            else:
                netmask = str(ipv4_network.netmask)  # e.g. '255.255.255.0'
            cls.logger.debug("Network mask: %r is %r", dn, netmask)
            cls._netmask_cache[dn] = netmask
        return cls._netmask_cache[dn]

    class Meta:
        udm_module = "networks/network"


class DNSReverseZone(UCSSchoolHelperAbstractClass):
    name = SubnetName(_("Subnet"))
    school = None

    @classmethod
    def get_container(cls, school: str = None) -> str:
        return "cn=dns,%s" % ucr.get("ldap/base")

    async def do_create(self, udm_obj: UdmObject, lo: UDM) -> None:
        udm_obj.props.nameserver = ucr.get("ldap/master")
        udm_obj.props.contact = "root@%s" % ucr.get("domainname")
        return await super(DNSReverseZone, self).do_create(udm_obj, lo)

    class Meta:
        udm_module = "dns/reverse_zone"
