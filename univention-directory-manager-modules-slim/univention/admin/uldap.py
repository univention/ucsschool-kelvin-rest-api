# -*- coding: utf-8 -*-

# Copyright 2020 Univention GmbH
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

from typing import Tuple

import univention.admin.uldap_docker as uldap_docker


class access(uldap_docker.access):
    pass


class Position(object):
    def __init__(self, dn: str) -> None:
        self.dn = dn

    def getDn(self) -> str:
        return self.dn

    def setDn(self, dn: str) -> None:
        self.dn = dn

    def __repr__(self) -> str:
        return self.dn


def position(base) -> Position:
    return Position(base)


LoType = access
PoType = Position


def getAdminConnection(*args, **kwargs) -> Tuple[LoType, PoType]:
    lo = uldap_docker.getAdminConnection(*args, **kwargs)
    po = Position(lo.base)
    return lo, po


def getMachineConnection(*args, **kwargs) -> Tuple[LoType, PoType]:
    lo = uldap_docker.getMachineConnection(*args, **kwargs)
    po = Position(lo.base)
    return lo, po
