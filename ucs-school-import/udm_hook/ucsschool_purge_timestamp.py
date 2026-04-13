#!/usr/bin/python2.7

# SPDX-FileCopyrightText: 2017 - 2026 Univention GmbH
# SPDX-License-Identifier: AGPL-3.0-only

import datetime
import re

from univention.admin.hook import simpleHook


class UcsschoolPurgeTimestamp(simpleHook):
    ldap_date_format = "%Y%m%d%H%M%SZ"
    udm_date_format = "%Y-%m-%d"
    udm_date_format_pattern = re.compile(r"\d\d\d\d-\d\d-\d\d")

    def hook_open(self, module):
        old_purge_ts = module.get("ucsschoolPurgeTimestamp")
        if old_purge_ts and not self.udm_date_format_pattern.match(old_purge_ts):
            module["ucsschoolPurgeTimestamp"] = self.ldap2udm(old_purge_ts)
            module.save()

    def hook_ldap_addlist(self, module, al=None):
        if al is None:
            al = []
        if module.info.get("ucsschoolPurgeTimestamp"):
            al = self.convert_ts_in_list(al)
        return al

    def hook_ldap_modlist(self, module, ml=None):
        if ml is None:
            ml = []
        if module.hasChanged("ucsschoolPurgeTimestamp"):
            ml = self.convert_ts_in_list(ml)
        return ml

    @classmethod
    def convert_ts_in_list(cls, add_mod_list):
        """Convert timestamp format in the list."""
        for item in [it for it in add_mod_list if it[0] == "ucsschoolPurgeTimestamp"]:
            if len(item) == 2:
                attr, add_val = item
                remove_val = ""
            else:
                attr, remove_val, add_val = item

            new_val = cls.udm2ldap(add_val)
            if cls.udm_date_format_pattern.match(remove_val):
                # LDAP value was converted on open(), convert back to original value
                remove_val = cls.udm2ldap(remove_val)
            add_mod_list.remove(item)
            add_mod_list.append(("ucsschoolPurgeTimestamp", remove_val, new_val))
        return add_mod_list

    @classmethod
    def ldap2udm(cls, ldap_val):
        """Convert '20090101000000Z' to '2009-01-01'. Ignores timezones."""
        if not ldap_val:
            return ""
        ldap_date = datetime.datetime.strptime(ldap_val, cls.ldap_date_format)
        return ldap_date.strftime(cls.udm_date_format)

    @classmethod
    def udm2ldap(cls, udm_val):
        """Convert '2009-01-01' to '20090101000000Z'. Ignores timezones."""
        if not udm_val:
            return ""
        udm_date = datetime.datetime.strptime(udm_val, cls.udm_date_format)
        return udm_date.strftime(cls.ldap_date_format)
