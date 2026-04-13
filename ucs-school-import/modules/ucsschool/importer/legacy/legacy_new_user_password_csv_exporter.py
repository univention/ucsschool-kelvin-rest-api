# SPDX-FileCopyrightText: 2026 Univention GmbH
# SPDX-License-Identifier: AGPL-3.0-only

"""
Write the passwords of newly created users to a CSV file.
"""

from csv import excel_tab

from ..configuration import Configuration
from ..writer.new_user_password_csv_exporter import NewUserPasswordCsvExporter


class LegacyNewUserPasswordCsvExporter(NewUserPasswordCsvExporter):
    """
    Export passwords of new users to a CSV file.

    Recreate line from legacy import script:
    OUTFILE.write("%s\t%s\t%s" % (person.login, password, line))
    """

    field_names = (
        "username",
        "password",
        "action",
        "name",
        "lastname",
        "firstname",
        "school",
        "school_classes",
        "ignore",
        "email",
        "is_teacher",
        "activate",
        "is_staff",
    )

    def __init__(self, *arg, **kwargs):
        super(LegacyNewUserPasswordCsvExporter, self).__init__(*arg, **kwargs)
        self.config = Configuration()

    def get_writer(self):
        """
        Change to CSV dialect with tabs and don't write a header line.
        """
        writer = self.factory.make_user_writer(field_names=self.field_names, dialect=excel_tab)
        writer.write_header = lambda x: None  # no header line
        return writer

    def serialize(self, user):
        res = dict(username=user.name, password=user.password)
        input_data = list(user.input_data)
        line = zip(self.field_names[2:], input_data)
        res.update(line)
        return res
