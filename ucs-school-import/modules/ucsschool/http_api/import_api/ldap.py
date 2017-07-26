# -*- coding: utf-8 -*-
"""
LDAP operations
"""
#
# Univention UCS@school
#
# Copyright 2017 Univention GmbH
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

from __future__ import absolute_import, unicode_literals
from ldap.filter import escape_filter_chars
from ucsschool.importer.utils.ldap_connection import get_admin_connection, get_machine_connection


def get_ous(ou=None):
	lo, po = get_machine_connection()
	if ou:
		return lo.search(filter='(&(objectClass=ucsschoolOrganizationalUnit)(ou={}))'.format(escape_filter_chars(ou)))
	else:
		return lo.search(filter='objectClass=ucsschoolOrganizationalUnit')
