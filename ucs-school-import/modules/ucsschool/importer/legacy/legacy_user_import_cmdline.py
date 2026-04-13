#!/usr/bin/python2.7

# SPDX-FileCopyrightText: 2026 Univention GmbH
# SPDX-License-Identifier: AGPL-3.0-only

"""
UCS@school legacy import tool cmdline frontend.
"""

from ucsschool.lib.models.utils import stopped_notifier

from ..frontend.user_import_cmdline import UserImportCommandLine
from ..utils.utils import nullcontext
from .legacy_user_import_parse_cmdline import LegacyUserImportParseUserImportCmdline


class LegacyUserImportCommandLine(UserImportCommandLine):
    def parse_cmdline(self):
        parser = LegacyUserImportParseUserImportCmdline()
        self.args = parser.parse_cmdline()

    @property
    def configuration_files(self):
        """
        Add legacy user import specific configuration files.

        :return: list of filenames
        :rtype: list(str)
        """
        res = super(LegacyUserImportCommandLine, self).configuration_files
        res.append("/usr/share/ucs-school-import/configs/user_import_legacy_defaults.json")
        res.append("/var/lib/ucs-school-import/configs/user_import_legacy.json")
        if self.args.conffile:
            res.append(self.args.conffile)
        return res

    async def do_import(self):
        importer = self.factory.make_mass_importer(self.config["dry_run"])
        with nullcontext() if self.config["dry_run"] else stopped_notifier():
            await importer.import_users()
        self.errors = importer.errors
