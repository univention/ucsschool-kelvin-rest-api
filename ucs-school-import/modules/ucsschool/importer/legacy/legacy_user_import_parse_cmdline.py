# SPDX-FileCopyrightText: 2026 Univention GmbH
# SPDX-License-Identifier: AGPL-3.0-only

"""
Legacy command line frontend for user import.
"""

import os
import os.path
import sys
from argparse import ArgumentParser

from ..frontend.parse_user_import_cmdline import ParseUserImportCmdline


class LegacyUserImportParseUserImportCmdline(ParseUserImportCmdline):
    def __init__(self):
        self.defaults = dict()
        self.parser = ArgumentParser(
            description="Create/modify/delete user accounts according to import file for UCS@school."
        )
        self.parser.add_argument("importFile", help="CSV file with users to import [mandatory].")
        self.parser.add_argument(
            "-c",
            "--conffile",
            help="Configuration file to use (e.g. "
            "/var/lib/ucs-school-import/configs/user_import_legacy.json).",
        )
        self.parser.add_argument(
            "-o", "--outfile", dest="outfile", help="File to write passwords of created users to."
        )

    def parse_cmdline(self):
        super(LegacyUserImportParseUserImportCmdline, self).parse_cmdline()

        # legacy cmdline tool output emulation
        print("infile is: {}".format(self.args.importFile))
        if not os.access(self.args.importFile, os.R_OK):
            print("ERROR: cannot read input data file '{}'.".format(self.args.importFile))
            sys.exit(1)
        if self.args.outfile:
            if os.path.exists(self.args.outfile):
                print("ERROR: outfile exists, will not overwrite existing file.")
                sys.exit(1)
            else:
                print("outfile is: {}".format(self.args.outfile))

        try:
            self.args.settings["input"]["filename"] = self.args.importFile
        except KeyError:
            self.args.settings["input"] = {"filename": self.args.importFile}
        try:
            self.args.settings["output"]["new_user_passwords"] = self.args.outfile
        except KeyError:
            self.args.settings["output"] = {"new_user_passwords": self.args.outfile}
        self.args.verbose = True
        # adding "logfile" early makes early logging possible
        self.args.logfile = "/var/log/univention/ucs-school-import.log"
        # self.args.conffile = "/var/lib/ucs-school-import/configs/user_import_legacy.json"
        return self.args
