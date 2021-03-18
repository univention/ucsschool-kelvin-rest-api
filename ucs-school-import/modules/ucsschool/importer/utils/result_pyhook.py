# -*- coding: utf-8 -*-
#
# Univention UCS@school
# Copyright 2018-2021 Univention GmbH
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

"""
Base class for all Python based Result-Pyhooks.
"""

from ..mass_import.user_import import UserImportData
from .import_pyhook import ImportPyHook


class ResultPyHook(ImportPyHook):
    """
    Hook that is called after import has finished.

    The base class' :py:meth:`__init__()` provides the following attributes:

    * self.dry_run     # whether hook is executed during a dry-run (1)
    * self.lo          # LDAP connection object (2)
    * self.logger      # Python logging instance

    If multiple hook classes are found, hook functions with higher
    priority numbers run before those with lower priorities. None disables
    a function (no need to remove it / comment it out).

    (1) Hooks are only executed during dry-runs, if the class attribute
    :py:attr:`supports_dry_run` is set to `True` (default is `False`). Hooks
    with `supports_dry_run == True` must not modify LDAP objects.
    Therefore the LDAP connection object self.lo will be a read-only connection
    during a dry-run.
    (2) Read-write cn=admin connection in a real run, read-only cn=admin
    connection during a dry-run.
    """

    priority = {
        "user_result": None,
    }

    def user_result(self, user_import_data: UserImportData) -> None:
        """
        Run code after user import has finished. Relevant data from the
        UserImport class is passed to this hook, so result summaries etc are
        possible.

        :param UserImportData user_import_data: relevant data from the UserImport class
        :return: None
        """
        return None
