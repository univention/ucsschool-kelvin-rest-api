# -*- coding: utf-8 -*-
#
# Univention UCS@school
# Copyright 2016-2021 Univention GmbH
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
Create historically unique usernames/email addresses.
"""

from __future__ import absolute_import

import logging
import re
import string
from functools import lru_cache
from typing import Callable, Dict

import lazy_object_proxy
from ldap.dn import escape_dn_chars
from six import string_types

from univention.admin.uexceptions import noObject, objectExists

from ..configuration import Configuration
from ..exceptions import BadValueStored, FormatError, NameKeyExists, NoValueStored
from .ldap_connection import LoType, PoType, get_admin_connection, get_unprivileged_connection


class NameCounterStorageBackend(object):
    def create(self, name: str, value: int) -> None:
        """
        Store a value for a new name.

        :param str name: name
        :param int value: value to store
        :return: None
        :raises NameKeyExists: if a value is already stored to such a `name`
        """
        raise NotImplementedError()

    def modify(self, name: str, old_value: int, new_value: int) -> None:
        """
        Store a value for an existing name.

        :param str name: name
        :param int old_value: old value
        :param int new_value: new value
        :return: None
        :raises NameKeyExists: if no value is stored by that `name`
        """
        raise NotImplementedError()

    def retrieve(self, name: str) -> int:
        """
        Retrieve a value for a name.

        :param str name: name to retrieve
        :return: int
        :raises NoValueStored: if no value is stored by that `name`
        :raises BadValueStored: if the value has a bad format
        """
        raise NotImplementedError()

    def remove(self, name: str) -> None:
        """
        Remove a name from storage.

        :param str name: name
        :return: None
        """
        raise NotImplementedError()

    def purge(self) -> None:
        """
        Remove *all* names from storage. *NEVER* do this in a production environment!

        :return: None
        """
        raise NotImplementedError()


class LdapStorageBackend(NameCounterStorageBackend):
    """
    Prior to using this class, a node must exist in LDAP:
    'cn=unique-<attribute_name>,cn=ucsschool,cn=univention,<base>'.
    """

    def __init__(self, attribute_storage_name: str, lo: LoType = None, pos: PoType = None) -> None:
        if lo and pos:
            self.lo, _pos = lo, pos
        else:
            self.lo, _pos = get_admin_connection()
        self.ldap_base = "cn=unique-{},cn=ucsschool,cn=univention,{}".format(
            escape_dn_chars(attribute_storage_name), self.lo.base
        )

    def create(self, name: str, value: int) -> None:
        try:
            self.lo.add(
                "cn={},{}".format(escape_dn_chars(name), self.ldap_base),
                [
                    ("objectClass", [b"ucsschoolUsername"]),
                    ("ucsschoolUsernameNextNumber", [str(value).encode("utf-8")]),
                ],
            )
        except objectExists:
            raise NameKeyExists("Cannot create key {!r} - already exists.".format(name))

    def modify(self, name: str, old_value: int, new_value: int) -> None:
        try:
            self.lo.modify(
                "cn={},{}".format(escape_dn_chars(name), self.ldap_base),
                [
                    (
                        "ucsschoolUsernameNextNumber",
                        str(old_value).encode("utf-8"),
                        str(new_value).encode("utf-8"),
                    )
                ],
            )
        except noObject:
            raise NoValueStored("Name {!r} not found.".format(name))

    def retrieve(self, name: str) -> int:
        try:
            res = self.lo.get(
                "cn={},{}".format(escape_dn_chars(name), self.ldap_base),
                attr=["ucsschoolUsernameNextNumber"],
            )["ucsschoolUsernameNextNumber"][0]
        except (KeyError, noObject):
            raise NoValueStored("Name {!r} not found.".format(name))
        try:
            return int(res)
        except ValueError as exc:
            raise BadValueStored("Value for name {!r} has wrong format: {}".format(name, exc))

    def remove(self, name: str) -> None:
        try:
            self.lo.delete("cn={},{}".format(escape_dn_chars(name), self.ldap_base))
        except noObject:
            pass

    def purge(self) -> None:
        """
        Remove *all* names from storage. *NEVER* do this in a production environment!

        :return: None
        """
        for dn, attribs in self.lo.search(
            filter="objectClass=ucsschoolUsername", base=self.ldap_base, attr=[""]
        ):
            self.lo.delete(dn)


class MemoryStorageBackend(NameCounterStorageBackend):
    def __init__(self, attribute_storage_name: str) -> None:
        self._mem_store: Dict[str, int] = dict()
        lo, po = get_unprivileged_connection()
        self.ldap_backend = LdapStorageBackend(attribute_storage_name, lo, po)

    def create(self, name: str, value: int) -> None:
        self._mem_store[name] = value

    def modify(self, name: str, old_value: int, new_value: int) -> None:
        self._mem_store[name] = new_value

    def retrieve(self, name: str) -> int:
        try:
            res = self._mem_store[name]
        except KeyError:
            res = self.ldap_backend.retrieve(name)
            self._mem_store[name] = res
        return res

    def remove(self, name: str) -> None:
        """
        This will remove the key only from memory. It may still be stored in
        the LDAP backend.

        :param str name: name
        :return: None
        """
        try:
            del self._mem_store[name]
        except KeyError:
            pass

    def purge(self) -> None:
        """
        This will remove keys only from memory. They may still be stored in
        the LDAP backend.

        :return: None
        """
        self._mem_store = dict()


class UsernameHandler(object):
    """
    >>> BAD_CHARS = ''.join(sorted(set(map(chr, range(128))) - set(UsernameHandler(20).allowed_chars)))
    >>> UsernameHandler(20).format_username('Max.Mustermann')
    'Max.Mustermann'
    >>> UsernameHandler(20).format_username('Foo[COUNTER2][COUNTER2]')   # doctest: +IGNORE_EXCEPTION_DETAIL
    Traceback (most recent call last):
    ...
    FormatError:
    >>> UsernameHandler(20).format_username('.')
    ''
    >>> UsernameHandler(20).format_username('.Max.Mustermann.')
    'Max.Mustermann'
    >>> UsernameHandler(4).format_username('Max.Mustermann')
    'Max'
    >>> for c in BAD_CHARS:
    ...  assert 'Max' == UsernameHandler(20).format_username('Ma%sx' % (c,))
    ...
    >>> UsernameHandler(20).format_username('Max.Mustermann12.4567890')
    'Max.Mustermann12.456'
    >>> for c in '.1032547698ACBEDGFIHKJMLONQPSRUTWVYXZacbedgfihkjmlonqpsrutwvyxz':
    ...  assert 'Ma%sx' % (c,) == UsernameHandler(20).format_username('Ma%sx' % (c,))
    ...
    >>> UsernameHandler(20).format_username('Max[Muster]Mann')
    'MaxMusterMann'
    >>> UsernameHandler(20).format_username('Max[ALWAYSCOUNTER].Mustermann')
    'Max1.Mustermann'
    >>> UsernameHandler(20).format_username('Max[ALWAYSCOUNTER].Mustermann')
    'Max2.Mustermann'
    >>> UsernameHandler(20).format_username('Max[ALWAYSCOUNTER].Mustermann')
    'Max3.Mustermann'
    >>> UsernameHandler(20).format_username('Max[COUNTER2].Mustermann')
    'Max4.Mustermann'
    >>> UsernameHandler(20).format_username('Maria[ALWAYSCOUNTER].Musterfrau')
    'Maria1.Musterfrau'
    >>> UsernameHandler(20).format_username('Moritz[COUNTER2]')
    'Moritz'
    >>> UsernameHandler(20).format_username('Moritz[COUNTER2]')
    'Moritz2'
    >>> UsernameHandler(20).format_username('Foo[ALWAYSCOUNTER]')
    'Foo1'
    >>> for i, c in enumerate(BAD_CHARS + BAD_CHARS, 2):
    ...  username = UsernameHandler(20).format_username('Fo%so[ALWAYSCOUNTER]' % (c,))
    ...  assert 'Foo%d' % (i,) == username, (username, i, c)
    >>> UsernameHandler(8).format_username('aaaa[COUNTER2]bbbbcccc')
    'aaaab'
    >>> UsernameHandler(8).format_username('aaaa[COUNTER2]bbbbcccc')
    'aaaa2b'
    >>> UsernameHandler(8).format_username('bbbb[ALWAYSCOUNTER]ccccdddd')
    'bbbb1c'
    >>> UsernameHandler(8).format_username('bbbb[ALWAYSCOUNTER]ccccdddd')
    'bbbb2c'
    >>> UsernameHandler(20).format_username('..[ALWAYSCOUNTER]..')
    ''
    >>> UsernameHandler(20).format_username('[ALWAYSCOUNTER]')
    ''
    >>> UsernameHandler(20).format_username('[FOObar]')
    'FOObar'
    """

    attribute_name = "username"
    attribute_storage_name = "usernames"

    def __init__(self, max_length: int, dry_run: bool = True) -> None:
        """
        :param int max_length: created usernames will be no longer
        than this
        :param bool dry_run: if False use LDAP to store already-used usernames
        if True store for one run only in memory
        """
        self.max_length = max_length
        self.dry_run = dry_run
        self.logger = logging.getLogger(__name__)
        self.config = lazy_object_proxy.Proxy(lambda: Configuration())
        self.storage_backend = self.get_storage_backend()
        self.logger.debug("%r storage_backend=%r", self, self.storage_backend.__class__.__name__)
        self.replacement_variable_pattern = re.compile(
            r"(%s)" % "|".join(map(re.escape, self.counter_variable_to_function.keys())), flags=re.I
        )

    def __repr__(self) -> str:
        return "{}(max_length={!r}, dry_run={!r})".format(
            self.__class__.__name__, self.max_length, self.dry_run
        )

    @property
    @lru_cache(maxsize=1)
    def allowed_chars(self) -> str:
        return (
            string.ascii_letters + string.digits + str(self.config["username"]["allowed_special_chars"])
        )

    def get_storage_backend(self) -> NameCounterStorageBackend:
        """
        :return: NameCounterStorageBackend instance
        :rtype: NameCounterStorageBackend
        """
        if self.dry_run:
            return MemoryStorageBackend(attribute_storage_name=self.attribute_storage_name)
        else:
            return LdapStorageBackend(attribute_storage_name=self.attribute_storage_name)

    @lru_cache(maxsize=128)
    def bad_chars_to_translate_table(self, bad_chars: str) -> Dict[int, None]:
        return dict((ord(x), None) for x in bad_chars)

    def remove_bad_chars(self, name: str) -> str:
        """
        Remove characters disallowed for names.
        * Name must only contain numbers, letters and dots, and may not be 'admin'!
        * Name must not start or end in a dot.

        :param str name: name to check
        :return: copy of input, possibly modified
        :rtype: str
        """
        if not self.allowed_chars:
            return name

        bad_chars = "".join(set(name).difference(set(self.allowed_chars)))
        if bad_chars:
            self.logger.warning(
                "Removing disallowed characters %r from %s %r.",
                "".join(sorted(bad_chars)),
                self.attribute_name,
                name,
            )
        for char in self.config["username"]["allowed_special_chars"]:
            if name.startswith(char) or name.endswith(char):
                self.logger.warning(
                    "Removing disallowed character %r from start and end of %s %r.",
                    char,
                    self.attribute_name,
                    name,
                )
                name = name.strip(char)
        return str(name).translate(self.bad_chars_to_translate_table(bad_chars))

    def format_name(self, name: str, max_length: int = None) -> str:
        """
        Create a username/email from <name>, possibly replacing a counter variable.
        * This is intended to be called before/by/after ImportUser.format_from_scheme().
        * Supports inserting the counter anywhere in the name, as long as its
        length does not overflow max_length.
        * Only one counter variable is allowed.
        * Counters should run only to 999. The algorithm will not honor
        max_length for higher numbers!
        * Subclass->override counter_variable_to_function() and the called methods to support
        other schemes than [ALWAYSCOUNTER] and [COUNTER2] or change their meaning.

        :param str name: username/email, possibly a template
        :param int max_length: overwrite max length specified at object instanciation time
        :return: unique name
        :rtype: str
        :raises FormatError: if more than one counter variable was found in the scheme
        """
        assert isinstance(name, string_types)
        PATTERN_FUNC_MAXLENGTH = 3  # maximum a counter function can produce is len('999')
        username = name
        if not max_length:
            max_length = self.max_length

        match = self.replacement_variable_pattern.search(name)
        if match:
            func = self.counter_variable_to_function[match.group().upper()]
            cut_pos = max(0, max_length - PATTERN_FUNC_MAXLENGTH)

            # it's not allowed to have two [COUNTER] patterns
            if len(self.replacement_variable_pattern.findall(name)) >= 2:
                raise FormatError(
                    "More than one counter variable found in {} scheme {!r}.".format(
                        self.attribute_name, name
                    ),
                    name,
                    name,
                )

            # the variable must no be the [COUNTER] pattern
            without_pattern = self.replacement_variable_pattern.sub("", name)
            without_pattern = self.remove_bad_chars(without_pattern)

            if len(without_pattern) > cut_pos:
                without_pattern = without_pattern[:cut_pos]
                start, end = without_pattern[: match.start()], without_pattern[match.start() :]
                username = "%s%s%s" % (start, match.group(), end)
            counter = func(without_pattern) if without_pattern else ""
            username = self.replacement_variable_pattern.sub(counter, username)

        username = self.remove_bad_chars(username)

        if not match and len(name) > max_length:
            username = username[:max_length]
            self.logger.warning("%s %r too long, shortened to %r.", self.attribute_name, name, username)

        username = username.strip(".")
        return username

    def format_username(self, name: str) -> str:
        """
        Deprecated method. Please use format_name() instead.
        """
        return self.format_name(name)

    @property
    def counter_variable_to_function(self) -> Dict[str, Callable[[str], str]]:
        """
        Subclass->override this to support other variables than [ALWAYSCOUNTER]
        and [COUNTER2] or change their meaning. Add/Modify corresponding
        methods in your subclass.
        Variables have to start with '[', end with ']' and must be all
        upper case.

        :return: mapping: variable name -> function
        :rtype: dict
        """
        return {"[ALWAYSCOUNTER]": self.always_counter, "[COUNTER2]": self.counter2}

    def always_counter(self, name_base: str) -> str:
        """
        [ALWAYSCOUNTER]

        :param str name_base: the name without [ALWAYSCOUNTER]
        :return: number to append to name
        :rtype: str
        """
        return self.get_and_raise(name_base, "1")

    def counter2(self, name_base: str) -> str:
        """
        [COUNTER2]

        :param str name_base: the name without [COUNTER2]
        :return: number to append to name
        :rtype: str
        """
        return self.get_and_raise(name_base, "")

    def get_and_raise(self, name_base: str, initial_value: str) -> str:
        """
        Returns the current counter value or initial_value if unset and stores
        it raised by 1.

        :param str name_base: name without []
        :param str initial_value: lowest value
        :return: current counter value
        :rtype: str
        """
        try:
            num = self.storage_backend.retrieve(name_base)
            self.storage_backend.modify(name_base, num, num + 1)
            res = str(num)
        except NoValueStored:  # not handling BadValueStored, because a data corruption should stop the import
            res = initial_value
            self.storage_backend.create(name_base, 2)
        return res


class EmailHandler(UsernameHandler):
    """
    Create unique email addresses.
    * Maximum length of an email address is 254 characters.
    * Applies counters [ALWAYSCOUNTER/COUNTER2] to local part (left of @) only.
    """

    attribute_name = "email"
    attribute_storage_name = "email"

    def __init__(self, max_length: int = 254, dry_run: bool = True) -> None:
        """
        :param int max_length: maximum length of email address
        :param bool dry_run: if False use LDAP to store already-used email addresses
        if True store for one run only in memory
        """
        super(EmailHandler, self).__init__(max_length, dry_run)
        # almost everything is allowed in email addresses (with complicated restrictions)

    @property
    def allowed_chars(self) -> str:
        return ""

    def remove_bad_chars(self, name: str) -> str:
        """
        Space is actually allowed (inside a quoted string), but we'll remove
        it anyway. (Although technically allowed, not all mail servers support it.)
        """
        bad_chars = "".join(set(name).intersection(set(string.whitespace)))
        if bad_chars:
            self.logger.warning(
                "Removing disallowed characters %r from %s %r.",
                "".join(sorted(bad_chars)),
                self.attribute_name,
                name,
            )
        return str(name).translate(self.bad_chars_to_translate_table(bad_chars))

    def format_name(self, name: str, max_length: int = None) -> str:
        local_part, _at, domain_part = name.rpartition("@")
        max_length = max_length or self.max_length - len(domain_part) - 1  # 1 = len(@)
        if max_length < 1:
            raise FormatError("Maximum email length is to small.", name, name)
        local_part_new = super(EmailHandler, self).format_name(local_part, max_length)
        return "{}@{}".format(local_part_new, domain_part)
