# SPDX-FileCopyrightText: 2026 Univention GmbH
# SPDX-License-Identifier: AGPL-3.0-only

from __future__ import absolute_import

from ucsschool.lib.models.utils import exec_cmd
from univention.listener import ListenerModuleHandler


class SchoolCreationHttpApiUpdateListener(ListenerModuleHandler):
    # replaces the 70http_api_school_create 00_hook script

    class Configuration(object):
        name = "http_api_school_listener"
        description = "Updates the database for the http_api"
        ldap_filter = "(objectClass=ucsschoolOrganizationalUnit)"

    def _update_http_api(self):
        with self.as_root():
            self.logger.info("Syncing all schools in http api")
            retval = exec_cmd(
                ["/usr/share/pyshared/ucsschool/http_api/manage.py", "updateschools", "-a"],
                raise_exc=False,  # this looks like a silent fail?
            )
            if retval:
                self.logger.info("http_api says:{} {}".format(retval[1], retval[2]))

    def initialize(self):
        self._update_http_api()

    def create(self, dn, new):
        """
        Updates the database for the http_api

        :param dn: the dn of the new school
        :param new: the new school object
        :return:
        """
        self.logger.debug("dn: %r", dn)
        name = new["ou"][0]
        with self.as_root():
            self.logger.info("Update school {} in http api".format(name))
            retval = exec_cmd(
                ["/usr/share/pyshared/ucsschool/http_api/manage.py", "updateschools", "--ou", name],
                raise_exc=False,  # this looks like a silent fail?
            )
            if retval:
                self.logger.info("http_api says for {}:{} {}".format(name, retval[1], retval[2]))

    def remove(self, dn, old):
        # TODO or use a -rm later on
        # self._update_http_api()
        pass
