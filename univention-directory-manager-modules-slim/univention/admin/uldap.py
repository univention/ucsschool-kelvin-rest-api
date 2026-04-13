# -*- coding: utf-8 -*-

# SPDX-FileCopyrightText: 2026 Univention GmbH
# SPDX-License-Identifier: AGPL-3.0-only

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
