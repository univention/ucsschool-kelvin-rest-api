# -*- coding: utf-8 -*-

#
# Fork of the DictReader class from Python 2.7 csv.py.
# Fork done to access the row returned by the underlying csv.reader instance.
#
# Licensed under the same license as the original:
#

# SPDX-FileCopyrightText: 1991 - 1995 Stichting Mathematisch Centrum Amsterdam
# SPDX-FileCopyrightText: 2001 - 2010 Python Software Foundation
# SPDX-FileCopyrightText: 2010 - 2011 Piotr Ożarowski <piotr@debian.org>
# SPDX-FileCopyrightText: 2016 - 2026 Univention GmbH
# SPDX-License-Identifier: AGPL-3.0-only
# SPDX-License-Identifier: Python-2.0

from _csv import reader


class DictReader(object):
    def __init__(self, f, fieldnames=None, restkey=None, restval=None, dialect="excel", *args, **kwds):
        self._fieldnames = fieldnames  # list of keys for the dict
        self.restkey = restkey  # key to catch long rows
        self.restval = restval  # default value for short rows
        self.reader = reader(f, dialect, *args, **kwds)
        self.dialect = dialect
        self.line_num = 0
        self.row = []

    def __iter__(self):
        return self

    @property
    def fieldnames(self):
        if self._fieldnames is None:
            try:
                self._fieldnames = self.reader.next()
            except StopIteration:
                pass
        self.line_num = self.reader.line_num
        return self._fieldnames

    @fieldnames.setter
    def fieldnames(self, value):
        self._fieldnames = value

    def next(self):
        if self.line_num == 0:
            # Used only for its side effect.
            self.fieldnames
        self.row = self.reader.next()
        self.line_num = self.reader.line_num

        # unlike the basic reader, we prefer not to return blanks,
        # because we will typically wind up with a dict full of None
        # values
        while self.row == []:
            self.row = self.reader.next()
        d = dict(zip(self.fieldnames, self.row))
        lf = len(self.fieldnames)
        lr = len(self.row)
        if lf < lr:
            d[self.restkey] = self.row[lf:]
        elif lf > lr:
            for key in self.fieldnames[lr:]:
                d[key] = self.restval
        return d
