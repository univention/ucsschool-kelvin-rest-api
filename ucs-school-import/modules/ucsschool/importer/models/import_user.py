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
Representation of a user read from a file.
"""

import datetime
import re
import string
import warnings
from collections import defaultdict, namedtuple
from typing import Any, Dict, Iterable, List, Optional, Tuple, Type, TypeVar, Union, cast

import lazy_object_proxy
from ldap.filter import filter_format
from six import iteritems, string_types

from ucsschool.lib.models.attributes import RecordUID, SourceUID, ValidationError
from ucsschool.lib.models.base import NoObject, UDMPropertiesError, WrongObjectType
from ucsschool.lib.models.school import School
from ucsschool.lib.models.user import (
    ConcreteUserClass,
    Staff,
    Student,
    Teacher,
    TeachersAndStaff,
    User,
    UserTypeConverter,
)
from ucsschool.lib.models.utils import create_passwd, ucr
from ucsschool.lib.roles import (
    create_ucsschool_role_string,
    role_pupil,
    role_staff,
    role_student,
    role_teacher,
)
from udm_rest_client import UDM, UdmObject
from univention.admin import property as uadmin_property
from univention.admin.syntax import gid as gid_syntax
from univention.admin.uexceptions import noProperty, valueError, valueInvalidSyntax
from univention.config_registry import ConfigRegistry

from ..configuration import Configuration, ReadOnlyDict
from ..default_user_import_factory import DefaultUserImportFactory
from ..exceptions import (
    BadPassword,
    EmptyFormatResultError,
    EmptyMandatoryAttribute,
    InitialisationError,
    InvalidBirthday,
    InvalidClassName,
    InvalidEmail,
    InvalidSchoolClasses,
    InvalidSchools,
    MissingMailDomain,
    MissingMandatoryAttribute,
    MissingSchoolName,
    MissingUid,
    NotSupportedError,
    NoUsernameAtAll,
    UDMError,
    UDMValueError,
    UniqueIdError,
    UnknownDisabledSetting,
    UnknownProperty,
    UnknownSchoolName,
    UsernameToLong,
    UserValidationError,
)
from ..factory import Factory
from ..utils.format_pyhook import FormatPyHook
from ..utils.import_pyhook import get_import_pyhooks
from ..utils.ldap_connection import get_admin_connection, get_readonly_connection
from ..utils.username_handler import UsernameHandler
from ..utils.utils import get_ldap_mapping_for_udm_property

FunctionSignature = namedtuple("FunctionSignature", ["name", "args", "kwargs"])
UsernameUniquenessTuple = namedtuple("UsernameUniquenessTuple", ["record_uid", "source_uid", "dn"])
GLOBAL_SOURCE_UID = "global_source_uid"
ALLOWED_CHARS_IN_SCHOOL_CLASS_NAME = set(string.digits + string.ascii_letters + " -._")
UNIQUENESS = "uniqueness"


class ImportUser(User):
    """
    Representation of a user read from a file. Abstract class, please use one
    of its subclasses ImportStaff etc.

    An import profile and a factory must have been loaded, before the class
    can be used. A convenience module does this::

        from ucsschool.importer.utils.shell import *
        user = factory.make_import_user(roles)
    """

    source_uid: str = SourceUID("SourceUID")
    record_uid: str = RecordUID("RecordUID")

    config: ReadOnlyDict = lazy_object_proxy.Proxy(lambda: Configuration())
    no_overwrite_attributes: List[str] = lazy_object_proxy.Proxy(
        lambda: ucr.get(
            "ucsschool/import/generate/user/attributes/no-overwrite-by-schema", "mailPrimaryAddress uid"
        ).split()
    )
    if not no_overwrite_attributes:  # is true when no-overwrite-by-schema was set to ""
        no_overwrite_attributes = ["mailPrimaryAddress", "uid"]
    User.logger.debug("Used no-overwrite-attributes: {}".format(no_overwrite_attributes))
    _unique_ids: Dict[str, Dict[str, str]] = defaultdict(dict)
    factory: DefaultUserImportFactory = lazy_object_proxy.Proxy(lambda: Factory())
    ucr: ConfigRegistry = lazy_object_proxy.Proxy(lambda: ImportUser.factory.make_ucr())
    reader = lazy_object_proxy.Proxy(lambda: ImportUser.factory.make_reader())
    ldap_lo_ro = lazy_object_proxy.Proxy(lambda: get_readonly_connection()[0])
    ldap_lo_rw = lazy_object_proxy.Proxy(
        lambda: get_readonly_connection()[0]
        if ImportUser.config["dry_run"]
        else get_admin_connection()[0]
    )
    _username_handler_cache: Dict[Tuple[int, bool], UsernameHandler] = {}
    _unique_email_handler_cache: Dict[bool, UsernameHandler] = {}
    # non-Attribute attributes (not in self._attributes) that can also be used
    # as arguments for object creation and will be exported by to_dict():
    _additional_props = (
        "action",
        "entry_count",
        "udm_properties",
        "input_data",
        "old_user",
        "in_hook",
        "roles",
    )
    prop = uadmin_property("_replace")
    _all_school_names: List[str] = None
    _all_usernames: Dict[str, UsernameUniquenessTuple] = {}
    _prop_regex = re.compile(r"<(.*?)(:.*?)*>")
    _prop_providers = {
        "birthday": "make_birthday",
        "expiration_date": "make_expiration_date",
        "firstname": "make_firstname",
        "lastname": "make_lastname",
        "email": "make_email",
        "record_uid": "make_record_uid",
        "source_uid": "make_source_uid",
        "school": "make_school",
        "name": "make_username",
        "username": "make_username",
        "ucsschool_roles": "make_ucsschool_roles",
    }

    def __init__(self, name=None, school=None, **kwargs):  # type: (str, str, **str) -> None
        """
        Create ImportUser object (neither saved nor loaded from LDAP yet).
        The `dn` attribute is calculated.

        :param str name: username
        :param str school: OU
        :param kwargs: attributes to set on user object
        """
        self.action: str = None  # "A", "D" or "M"
        self.entry_count = 0  # line/node number of input data
        # UDM properties from input, that are not stored in Attributes:
        self.udm_properties: Dict[str, Any] = {}
        self.input_data: List[str] = []  # raw input data created by SomeReader.read()
        self.old_user: ImportUser = None  # user in LDAP, when modifying
        self.in_hook = False  # if a hook is currently running

        self._lo: UDM = None

        for attr in self._additional_props:
            try:
                val = kwargs.pop(attr)
                setattr(self, attr, val)
            except KeyError:
                pass

        self._purge_ts = None  # type: str
        # recursion prevention:
        self._used_methods: Dict[str, List[FunctionSignature]] = defaultdict(list)
        self.lo: UDM = kwargs.pop("lo", None)
        super(ImportUser, self).__init__(name, school, **kwargs)

    @staticmethod
    def _pyhook_supports_dry_run(kls: Type["ImportUser"]) -> bool:
        return bool(getattr(kls, "supports_dry_run", False))

    async def call_hooks(self, udm: UDM, hook_time: str, func_name: str) -> Optional[bool]:
        """
        Runs Kelvin PyHooks.

        :param UDM udm: UDM REST Client instance
        :param str hook_time: `pre` or `post`
        :param str func_name: `create`, `modify`, `move` or `remove`
        :return: legacy: return code of lib hooks (always `None` in Kelvin)
        :rtype: bool: result of a legacy hook or None if no legacy hook ran
                (always `None` in Kelvin)
        """
        if (
            hook_time == "post"
            and self.action in ["A", "M"]
            and not (self.config["dry_run"] and self.action == "A")
        ):
            # update self from LDAP if object exists (after A and M), except after a dry-run create
            user = await self.get_by_import_id(udm, self.source_uid, self.record_uid)
            user_udm = await user.get_udm_object(udm)
            # copy only those UDM properties from LDAP that were originally
            # set in self.udm_properties
            for k in self.udm_properties.keys():
                user.udm_properties[k] = user_udm.props[k]
            self.update(user)

        self.in_hook = True
        hooks = get_import_pyhooks(
            "ucsschool.importer.utils.user_pyhook.UserPyHook",
            self._pyhook_supports_dry_run if self.config["dry_run"] else None,
            lo=self.ldap_lo_rw,
            dry_run=self.config["dry_run"],
            udm=udm,
        )  # result is cached on the lib side
        meth_name = "{}_{}".format(hook_time, func_name)
        try:
            for func in hooks.get(meth_name, []):
                func.__self__.udm = udm  # update UDM instance to the current one
                self.logger.debug(
                    "Running %s hook %s.%s for %s...",
                    meth_name,
                    func.__self__.__class__.__name__,
                    func.__name__,
                    self,
                )
                await func(self)
        finally:
            self.in_hook = False
        return None

    def call_format_hook(self, prop_name, fields):  # type: (str, Dict[str, Any]) -> Dict[str, Any]
        """
        Run format hooks.

        :param str prop_name: the property for format
        :param dict fields: dictionary to manipulate in hook, will be used later to format the property
        :return: manipulated dictionary
        :rtype: dict
        """
        hooks = get_import_pyhooks(FormatPyHook)  # result is cached on the lib side
        res = fields
        for func in hooks.get("patch_fields_{}".format(self.role_sting), []):
            hook_class = func.__self__.__class__
            if prop_name not in hook_class.properties:
                # ignore properties not in Hook.properties
                continue
            self.logger.debug(
                "Running patch_fields_%s hook %s for property name %r for user %s...",
                self.role_sting,
                func,
                prop_name,
                self,
            )
            res = func(prop_name, res)
        return res

    async def change_school(self, school, lo):  # type: (str, UDM) -> bool
        """
        Change primary school of user.

        :param str school: new OU
        :param univention.admin.uldap.access connection lo: LDAP connection object
        :return: whether the school change succeeded
        :rtype: bool
        """
        await self.check_schools(lo, additional_schools=[school])
        await self.validate(lo, validate_unlikely_changes=True, check_username=False)
        if self.errors:
            raise UserValidationError(
                "ValidationError when moving {} from {!r} to {!r}.".format(self, self.school, school),
                validation_error=ValidationError(self.errors.copy()),
            )
        old_dn = self.old_dn
        res = await super(ImportUser, self).change_school(school, lo)
        if res and UNIQUENESS not in self.config.get("skip_tests", []):
            # rewrite _unique_ids and _all_usernames, replacing old DN with new DN
            self._unique_ids_replace_dn(old_dn, self.dn)
            self._all_usernames[self.name] = UsernameUniquenessTuple(
                self.record_uid, self.source_uid, self.dn
            )
        return res

    @classmethod
    def _unique_ids_replace_dn(cls, old_dn, new_dn):  # type: (str, str) -> None
        """Change a DN in unique_ids store."""
        for category, entries in cls._unique_ids.items():
            for value, dn in entries.items():
                if dn == old_dn:
                    cls._unique_ids[category][value] = new_dn

    async def check_schools(self, lo: UDM, additional_schools: Optional[Iterable[str]] = None) -> None:
        """
        Verify that the "school" and "schools" attributes are correct.
        Check is case sensitive (Bug #42456).

        :param univention.admin.uldap.access connection lo: LDAP connection object
        :param additional_schools: list of school name to check additionally to the one in self.schools
        :type additional_schools: list(str)
        :return: None
        :rtype: None
        :raises UnknownSchoolName: if a school is not known
        """
        schools = set(self.schools)
        schools.add(self.school)
        if additional_schools:
            schools.update(additional_schools)
        all_school_names = await self.get_all_school_names(lo)
        for school in schools:
            if school not in all_school_names:
                # retry for case where create_ou ran parallel to this process
                # may happen with HTTP-API
                self.__class__._all_school_names = []
                all_school_names = await self.get_all_school_names(lo)
                if school in all_school_names:
                    continue
                self.logger.debug("Known schools: %r", all_school_names)
                raise UnknownSchoolName(
                    "School {!r} does not exist.".format(school),
                    input=self.input_data,
                    entry_count=self.entry_count,
                    import_user=self,
                )

    async def create(self, lo, validate=True):  # type: (UDM, Optional[bool]) -> bool
        """
        Create user object.

        :param univention.admin.uldap.access connection lo: LDAP connection object
        :param bool validate: if the users attributes should be checked by UDM
        :return: whether the object created succeeded
        :rtype: bool
        """
        self.lo = lo
        if self.in_hook:
            # prevent recursion
            self.logger.warning("Running create() from within a hook.")
            res = await self.create_without_hooks(lo, validate)
        else:
            res = await super(ImportUser, self).create(lo, validate)
        if UNIQUENESS not in self.config.get("skip_tests", []):
            self._all_usernames[self.name] = UsernameUniquenessTuple(
                self.record_uid, self.source_uid, self.dn
            )
        return res

    async def create_without_hooks_roles(self, lo: UDM) -> None:
        if self.config["dry_run"]:
            self.logger.info("Dry-run: skipping user.create() for %s.", self)
            return True
        else:
            return await super(ImportUser, self).create_without_hooks_roles(lo)

    @classmethod
    def get_ldap_filter_for_user_role(cls):  # type: () -> str
        # convert cmdline / config name to ucsschool.lib role(s)
        if not cls.config["user_role"]:
            roles = ()  # type: Iterable[str]
        elif cls.config["user_role"] == "student":
            roles = (role_pupil,)
        elif cls.config["user_role"] == "teacher_and_staff":
            roles = (role_teacher, role_staff)
        else:
            roles = (cls.config["user_role"],)
        a_user = cls.factory.make_import_user(roles)
        return a_user.type_filter

    @classmethod
    async def get_by_import_id(cls, connection, source_uid, record_uid, superordinate=None):
        # type: (UDM, str, str, Optional[str]) -> ImportUser
        """
        Retrieve an ImportUser.

        :param univention.admin.uldap.access connection: uldap object
        :param str source_uid: source DB identifier
        :param str record_uid: source record identifier
        :param str superordinate: superordinate
        :return: object of :py:class:`ImportUser` subclass loaded from LDAP or raises NoObject
        :rtype: ImportUser
        :raises ucsschool.lib.models.base.NoObject: if no user was found
        """
        if not source_uid or not record_uid:
            raise MissingUid(
                "source_uid or record_uid are not set (source_uid={!r} record_uid={!r}).".format(
                    source_uid, record_uid
                )
            )

        oc_filter = cls.get_ldap_filter_for_user_role()
        filter_s = filter_format(
            "(&{}(ucsschoolSourceUID=%s)(ucsschoolRecordUID=%s))".format(oc_filter),
            (source_uid, record_uid),
        )
        obj = await cls.get_only_udm_obj(connection, filter_s, superordinate=superordinate)
        if obj:
            return await cls.from_udm_obj(obj, None, connection)
        else:
            dns = cls.ldap_lo_ro.searchDn(
                filter_format(
                    "(&(ucsschoolSourceUID=%s)(ucsschoolRecordUID=%s))", (source_uid, record_uid)
                )
            )
            if dns:
                raise WrongObjectType(dns[0], cls)
            else:
                raise NoObject(
                    "No {} with source_uid={!r} and record_uid={!r} found.".format(
                        cls.config.get("user_role", "user") or "User", source_uid, record_uid
                    )
                )

    def deactivate(self):  # type: () -> None
        """
        Deactivate user account. Caller must run modify().
        """
        self.disabled = True

    def expire(self, expiry):  # type: (str) -> None
        """
        Set the account expiration date. Caller must run modify().

        :param str expiry: expire date "%Y-%m-%d" or ""

        .. deprecated:: 4.4 v9
            Use `user.self.expiration_date = expiry` instead.
        """
        self.expiration_date = expiry
        warnings.warn(
            "The method User.expire(expiry) is deprecated. Set the expiration date with "
            "'user.expiration_date = expiry'.",
            PendingDeprecationWarning,
        )

    @classmethod
    def from_dict(cls, a_dict):  # type: (Dict[str, Any]) -> ImportUser
        """
        Create user object from a dictionary created by `to_dict()`.

        :param dict a_dict: dictionary created by `to_dict()`
        :return: ImportUser instance
        :rtype: ImportUser
        """
        assert isinstance(a_dict, dict)
        user_dict = a_dict.copy()
        for attr in ("$dn$", "objectType", "type", "type_name"):
            # those should be generated upon creation
            try:
                del user_dict[attr]
            except KeyError:
                pass
        roles = user_dict.pop("roles", [])
        return cls.factory.make_import_user(roles, **user_dict)

    def _handle_udm_properties(self, udm_obj: UdmObject):
        try:
            super(ImportUser, self)._handle_udm_properties(udm_obj)
        except UDMPropertiesError as exc:
            raise UDMError(exc.message, entry_count=self.entry_count, import_user=self) from exc

    async def _alter_udm_obj(self, udm_obj):  # type: (UdmObject) -> None
        await super(ImportUser, self)._alter_udm_obj(udm_obj)
        if self._purge_ts is not None:
            udm_obj.props["ucsschoolPurgeTimestamp"] = self._purge_ts

    @classmethod
    async def get_all_school_names(cls, lo: UDM) -> Iterable[str]:
        if not cls._all_school_names:
            cls._all_school_names = [s.name for s in await School.get_all(lo)]
        return cls._all_school_names

    async def has_purge_timestamp(self, connection: UDM) -> bool:
        """
        Check if the user account has a purge timestamp set (regardless if it is
        in the future or past).

        :param univention.admin.uldap.access connection: uldap connection object
        :return: whether the user account has a purge timestamp set
        :rtype: bool
        """
        user_udm = await self.get_udm_object(connection)
        return bool(user_udm["ucsschoolPurgeTimestamp"])

    async def has_expired(self, connection: UDM) -> bool:
        """
        Check if the user account has expired.

        :param univention.admin.uldap.access connection: uldap connection object
        :return: whether the user account has expired
        :rtype: bool
        """
        if not self.expiration_date:
            return False
        expiry = datetime.datetime.strptime(self.expiration_date, "%Y-%m-%d")
        return datetime.datetime.now() > expiry

    async def has_expiry(self, connection: UDM) -> bool:
        """
        Check if the user account has an expiry date set (regardless if it is
        in the future or past).

        :param univention.admin.uldap.access connection: uldap connection object
        :return: whether the user account has an expiry date set
        :rtype: bool
        """
        return bool(self.expiration_date)

    @property
    def lo(self):  # type: () -> UDM
        """
        LDAP connection object

        Read-write cn=admin connection in a real run, read-only cn=admin
        connection during a dry-run.
        """
        if not self._lo:
            raise RuntimeError(f"'self.lo' has not yet been set. self={self!r}")
            # self._lo, po = (
            #     get_readonly_connection() if self.config["dry_run"] else get_admin_connection()
            # )
        return self._lo

    @lo.setter
    def lo(self, value):  # type: (UDM) -> None
        cn_admin_dn = "cn=admin,{}".format(ucr["ldap/base"])
        assert not (
            self.config["dry_run"] and value == cn_admin_dn
        )  # TODO: 1. compare with lo.lo.binddn, 2. don't use assert, raise an exception
        self._lo = value

    def prepare_all(self, new_user=False):  # type: (Optional[bool]) -> None
        """
        Necessary preparation to modify a user in UCS.
        Runs all make_* functions.

        :param bool new_user: if a password should be created
        :return: None
        """
        self.prepare_uids()
        self.prepare_udm_properties()
        self.prepare_attributes(new_user)

    def prepare_attributes(self, new_user=False):  # type: (Optional[bool]) -> None
        """
        Run make_* functions for all Attributes of ucsschool.lib.models.user.User.

        :param bool new_user: if a password should be created
        :return: None
        """
        self.make_firstname()
        self.make_lastname()
        self.make_school()
        self.make_schools()
        self.make_ucsschool_roles()
        self.make_username()
        if new_user:
            self.make_password()
        if self.password:
            self.udm_properties["overridePWHistory"] = True
            self.udm_properties["overridePWLength"] = True
        self.make_classes()
        self.make_birthday()
        self.make_disabled()
        self.make_email()
        self.make_expiration_date()

    def prepare_udm_properties(self):  # type: () -> None
        """
        Create self.udm_properties from schemes configured in config["scheme"].
        Existing entries will be overwritten unless listed in UCRV
        ucsschool/import/generate/user/attributes/no-overwrite-by-schema.

        * Attributes (email, record_uid, [user]name etc.) are ignored, as they are processed separately
            in make_*.
        * See /usr/share/doc/ucs-school-import/user_import_configuration_readme.txt.gz section "scheme"
            for details on the configuration.
        """
        ignore_keys = list(self.to_dict().keys())
        ignore_keys.extend(
            ["mailPrimaryAddress", "record_uid", "source_uid", "username"]
        )  # these are used in make_*
        ignore_keys.extend(self.no_overwrite_attributes)
        for prop in [k for k in self.config["scheme"].keys() if k not in ignore_keys]:
            self.make_udm_property(prop)

    def prepare_uids(self):  # type: () -> None
        """
        Necessary preparation to detect if user exists in UCS.
        Runs make_* functions for record_uid and source_uid Attributes of
        ImportUser.
        """
        self.make_record_uid()
        self.make_source_uid()

    def make_birthday(self):  # type: () -> Optional[str]
        """
        Set User.birthday attribute.
        """
        if self.birthday:
            try:
                self.birthday = self.parse_date(self.birthday)
            except ValueError:
                self.logger.error("Could not parse birthday.")
        elif self._schema_write_check("birthday", "birthday", "univentionBirthday"):
            self.birthday = self.format_from_scheme(
                "birthday", self.config["scheme"]["birthday"]
            )  # type: str
        elif self.old_user:
            self.birthday = self.old_user.birthday
        elif self.birthday == "":
            self.birthday = None
        return self.birthday

    def make_expiration_date(self):  # type: () -> Optional[str]
        """
        Set User.expiration_date attribute.
        """
        if self.expiration_date:
            self.logger.warning(
                "The expiration date is usually set by the import itself. Setting it manually may lead to errors in future imports."
            )
            try:
                self.expiration_date = self.parse_date(self.expiration_date)
            except ValueError:
                self.logger.error("Could not parse expiration date.")
        elif all(
            [
                self._schema_write_check("expiration_date", "userexpiry", ldap_attr)
                for ldap_attr in ["krb5ValidEnd", "shadowExpire", "sambaKickoffTime"]
            ]
        ):
            self.expiration_date = self.format_from_scheme(
                "expiration_date", self.config["scheme"]["expiration_date"]
            )  # type: str
        elif self.old_user:
            self.expiration_date = self.old_user.expiration_date
        if self.expiration_date == "":
            self.expiration_date = None
        return self.expiration_date

    def parse_date(self, text):  # type: (str) -> str
        re_1 = re.compile(r"^[0-9]{4}-[0-9]{2}-[0-9]{2}$")  # yyyy-mm-dd
        re_2 = re.compile(r"^[0-9]{2}\.[0-9]{2}\.[0-9]{2,4}$")  # dd.mm.yy or dd.mm.yyyy
        re_3 = re.compile(r"^[0-9]{2}/[0-9]{2}/[0-9]{2,4}$")  # mm/dd/yy or mm/dd/yyyy

        year, month, day = 0, 0, 0
        if re_1.match(text):
            year, month, day = map(int, text.split("-", 2))
        elif re_2.match(text):
            day, month, year = map(int, text.split(".", 2))
        elif re_3.match(text):
            month, day, year = map(int, text.split("/", 2))
        if 1 <= month <= 12 and 1 <= day <= 31:
            if 1900 < year < 2100:
                return "%d-%02d-%02d" % (year, month, day)
            if 0 <= year <= 99:
                if year <= datetime.date.today().year % 100:
                    return "20%02d-%02d-%02d" % (year, month, day)
                return "19%02d-%02d-%02d" % (year, month, day)

        raise ValueError

    def make_classes(self):  # type: () -> Dict[str, Dict[str, List[str]]]
        """
        Create school classes.

        * This should run after make_school().
        * If attribute already exists as a dict, it is not changed.
        * Attribute is only written if it is set to a string like 'school1-cls2,school3-cls4'.
        """
        from ..reader.base_reader import BaseReader  # isort:skip  # prevent cyclic import

        char_replacement = self.config["school_classes_invalid_character_replacement"]
        if isinstance(self, Staff):
            self.school_classes = dict()  # type: Dict[str, Dict[str, List[str]]]
        elif isinstance(self.school_classes, dict) and self.school_classes:
            for school, classes in iteritems(self.school_classes):
                self.school_classes[school] = [
                    self.school_classes_invalid_character_replacement(class_name, char_replacement)
                    for class_name in classes
                ]
        elif isinstance(self.school_classes, dict) and not self.school_classes:
            self.reader = cast(BaseReader, self.reader)
            input_dict = self.reader.get_data_mapping(self.input_data)
            if input_dict.get("school_classes") == "":
                # mapping exists and csv field is empty -> empty property, except if config says
                # otherwise keep only classes of schools that the user is still a member of (Bug #49995)
                if self.old_user and self.config.get("school_classes_keep_if_empty", False):
                    self.logger.info(
                        "Reverting school_classes of %r to previous value %r.",
                        self,
                        self.old_user.school_classes,
                    )
                    self.school_classes = dict(
                        (school, classes)
                        for school, classes in iteritems(self.old_user.school_classes)
                        if school in self.schools
                    )
            elif "school_classes" not in input_dict:
                # no mapping -> try to get previous data
                if self.old_user:
                    self.school_classes = self.old_user.school_classes
            else:
                raise RuntimeError(
                    "Input data contains school_classes data, but self.school_classes is empty."
                )
        elif isinstance(self.school_classes, string_types):
            res = defaultdict(list)
            school_classes = cast(str, self.school_classes)
            self.school_classes = school_classes.strip(" \n\r\t,")
            for a_class in [klass.strip() for klass in self.school_classes.split(",") if klass.strip()]:
                school, sep, cls_name = [x.strip() for x in a_class.partition("-")]
                if sep and not cls_name:
                    raise InvalidClassName("Empty class name.")
                if not sep:
                    # no school prefix
                    if not self.school:
                        self.make_school()
                    cls_name = school
                    school = self.school
                cls_name = self.normalize(cls_name)
                school = self.normalize(school)
                klass_name = self.school_classes_invalid_character_replacement(
                    "{}-{}".format(school, cls_name), char_replacement
                )
                if klass_name not in res[school]:
                    res[school].append(klass_name)
            self.school_classes = dict(res)
        elif self.school_classes is None:
            self.school_classes = dict()
        else:
            raise RuntimeError(
                "Unknown data in attribute 'school_classes': {!r}".format(self.school_classes)
            )
        return self.school_classes

    def make_disabled(self):  # type: () -> bool
        """
        Set User.disabled attribute.
        """
        if self.disabled is not None:
            return self.disabled

        try:
            activate = self.config["activate_new_users"][self.role_sting]
        except KeyError:
            try:
                activate = self.config["activate_new_users"]["default"]
            except KeyError:
                raise UnknownDisabledSetting(
                    "Cannot find 'disabled' ('activate_new_users') setting for role '{}' or "
                    "'default'.".format(self.role_sting),
                    self.entry_count,
                    import_user=self,
                )
        self.disabled = not bool(activate)
        return self.disabled

    def make_firstname(self):  # type: () -> str
        """
        Normalize given name if set from import data or create from scheme.
        """
        if self.firstname:
            if self.config.get("normalize", {}).get("firstname", False):
                self.firstname = self.normalize(self.firstname)  # type: str
        elif self._schema_write_check("firstname", "firstname", "givenName"):
            self.firstname = self.format_from_scheme("firstname", self.config["scheme"]["firstname"])
        elif self.old_user:
            self.firstname = self.old_user.firstname
        return self.firstname or ""

    def make_lastname(self):  # type: () -> str
        """
        Normalize family name if set from import data or create from scheme.
        """
        if self.lastname:
            if self.config.get("normalize", {}).get("lastname", False):
                self.lastname = self.normalize(self.lastname)  # type: str
        elif self._schema_write_check("lastname", "lastname", "sn"):
            self.lastname = self.format_from_scheme("lastname", self.config["scheme"]["lastname"])
        elif self.old_user:
            self.lastname = self.old_user.lastname
        return self.lastname or ""

    def make_email(self):  # type: () -> str
        """
        Create email from scheme (if not already set).

        If any of the other attributes is used in the format scheme of the
        email address, its make_* function should have run before this!
        """
        if self.email is not None:  # allow to remove an email address with self.email == ''
            pass
        elif self.udm_properties.get("mailPrimaryAddress"):
            self.email = self.udm_properties.pop("mailPrimaryAddress")  # type: str
        elif self._schema_write_check("email", "email", "mailPrimaryAddress"):
            maildomain = self.config.get("maildomain")
            if not maildomain:
                try:
                    # TODO: not available (yet) in Docker container
                    maildomain = ucr["mail/hosteddomains"].split()[0]
                except (AttributeError, IndexError):
                    if (
                        "email" in self.config["mandatory_attributes"]
                        or "mailPrimaryAttribute" in self.config["mandatory_attributes"]
                    ):
                        raise MissingMailDomain(
                            "Could not retrieve mail domain from configuration nor from UCRV "
                            "mail/hosteddomains.",
                            entry_count=self.entry_count,
                            import_user=self,
                        )
                    else:
                        return self.email
            self.email = self.format_from_scheme(
                "email", self.config["scheme"]["email"], maildomain=maildomain
            ).lower()
            try:
                self.email = self.unique_email_handler.format_name(self.email)
            except EmptyFormatResultError:
                if (
                    "email" in self.config["mandatory_attributes"]
                    or "mailPrimaryAttribute" in self.config["mandatory_attributes"]
                ):
                    raise
        elif self.old_user:  # allow to retain existing old email address with self.email == None
            self.email = self.old_user.email
        return self.email or ""

    def make_password(self):  # type: () -> str
        """
        Create random password (if not already set).
        """
        if not self.password:
            self.password = create_passwd(self.config["password_length"])  # type: str
        return self.password

    def make_record_uid(self):  # type: () -> str
        """
        Create ucsschoolRecordUID (record_uid) (if not already set).
        """
        if self.record_uid:
            pass
        elif self._schema_write_check("record_uid", "record_uid", "ucsschoolRecordUID"):
            self.record_uid = self.format_from_scheme(
                "record_uid", self.config["scheme"]["record_uid"]
            )  # type: str
        elif self.old_user:
            self.record_uid = self.old_user.record_uid
        return self.record_uid or ""

    def make_source_uid(self):  # type: () -> str
        """
        Set the ucsschoolSourceUID (source_uid) (if not already set).
        """
        if self.source_uid:
            if self.source_uid != self.config["source_uid"] and GLOBAL_SOURCE_UID not in self.config.get(
                "skip_tests", []
            ):
                raise NotSupportedError(
                    "Source_uid '{}' differs to configured source_uid '{}'.".format(
                        self.source_uid, self.config["source_uid"]
                    )
                )
        else:
            self.source_uid = self.config["source_uid"]  # type: str
        return self.source_uid or ""

    def make_school(self):  # type: () -> str
        """
        Create 'school' attribute - the position of the object in LDAP (if not already set).

        Order of detection:

        * already set (object creation or reading from input)
        * from configuration (file or cmdline)
        * first (alphanum-sorted) school in attribute schools
        """
        if self.school:
            self.school = self.normalize(self.school)  # type: str
        elif self.config.get("school"):
            self.school = self.config["school"]
        elif self.schools and isinstance(self.schools, list):
            self.school = self.normalize(sorted(self.schools)[0])
        elif self.schools and isinstance(self.schools, string_types):
            self.make_schools()  # this will recurse back, but schools will be a list then
        else:
            raise MissingSchoolName(
                "Primary school name (ou) was not set on the cmdline or in the configuration file and "
                "was not found in the input data.",
                entry_count=self.entry_count,
                import_user=self,
            )
        return self.school

    def make_schools(self):  # type: () -> List[str]
        """
        Create list of schools this user is in.
        If possible, this should run after make_school()

        * If empty, it is set to self.school.
        * If it is a string like 'school1,school2,school3' the attribute is created from it.
        """
        if self.schools and isinstance(self.schools, list):
            self.schools = list(set(self.schools))  # type: List[str]
        elif not self.schools:
            if not self.school:
                self.make_school()
            self.schools = [self.school]
        elif isinstance(self.schools, string_types):
            schools = cast(str, self.schools)
            self.schools = schools.strip(",").split(",")
            self.schools = sorted(set(self.normalize(s.strip()) for s in self.schools))
        else:
            raise RuntimeError("Unknown data in attribute 'schools': '{}'".format(self.schools))

        if not self.school:
            self.make_school()
        if self.school not in self.schools:
            if not self.schools:
                self.schools = [self.school]
            else:
                self.school = sorted(self.schools)[0]
        return self.schools

    def make_ucsschool_roles(self):  # type: () -> List[str]
        if self.ucsschool_roles:
            return self.ucsschool_roles
        if not self.schools:
            self.make_schools()
        self.ucsschool_roles = [
            create_ucsschool_role_string(role, school)
            for role in self.default_roles
            for school in self.schools
        ]  # type: List[str]
        return self.ucsschool_roles

    def make_udm_property(self, property_name):  # type: (str) -> Union[str, None]
        """
        Create :py:attr:`self.udm_properties[property_name]` from scheme if
        not already existent.

        :param str property_name: name of UDM property
        :return: value read from CSV or calculated from scheme or None
        :rtype: str or None
        """
        try:
            return self.udm_properties[property_name]
        except KeyError:
            pass

        ldap_attr = get_ldap_mapping_for_udm_property(property_name, self._meta.udm_module)
        if self._schema_write_check(property_name, property_name, ldap_attr):
            self.udm_properties[property_name] = self.format_from_scheme(
                property_name, self.config["scheme"][property_name]
            )
        return self.udm_properties.get(property_name)

    def make_username(self):  # type: () -> str
        """
        Create username if not already set in self.name or self.udm_properties["username"].
        [ALWAYSCOUNTER] and [COUNTER2] are supported, but only one may be used
        per name.
        """
        if self.name:
            return self.name
        elif self.udm_properties.get("username"):
            self.name = self.udm_properties.pop("username")  # type: str
        elif self._schema_write_check("username", "name", "uid"):
            self.name = self.format_from_scheme("username", self.username_scheme)
            if not self.name:
                raise EmptyFormatResultError(
                    "No username was created from scheme '{}'.".format(self.username_scheme),
                    self.username_scheme,
                    self.to_dict(),
                )
            self.name = self.username_handler.format_name(self.name)
            if not self.name:
                raise EmptyFormatResultError(
                    "Username handler transformed {!r} to empty username.".format(self.name),
                    self.username_scheme,
                    self.to_dict(),
                )
        elif self.old_user:
            self.name = self.old_user.name  # type: str
        return self.name or ""

    async def modify(self, lo, validate=True, move_if_necessary=None):
        # type: (UDM, Optional[bool], Optional[bool]) -> bool
        self.lo = lo
        if self.in_hook:
            # prevent recursion
            self.logger.warning("Running modify() from within a hook.")
            res = await self.modify_without_hooks(lo, validate, move_if_necessary)
        else:
            res = await super(ImportUser, self).modify(lo, validate, move_if_necessary)
        if (
            self.old_user
            and self.old_user.name != self.name
            and UNIQUENESS not in self.config.get("skip_tests", [])
        ):
            del self._all_usernames[self.old_user.name]
            self._all_usernames[self.name] = UsernameUniquenessTuple(
                self.record_uid, self.source_uid, self.dn
            )
        return res

    async def modify_without_hooks(
        self, lo: UDM, validate: bool = True, move_if_necessary: bool = None
    ) -> bool:
        if not self.school_classes and self.config.get("school_classes_keep_if_empty", False):
            # empty classes input means: don't change existing classes (Bug #42288)
            # except removing classes from schools that user is not a member of anymore (Bug #49995)
            udm_obj = await self.get_udm_object(lo)
            school_classes = await self.get_school_classes(udm_obj, self)
            self.logger.info(
                "Reverting school_classes of %r to %r, because school_classes_keep_if_empty=%r and new "
                "school_classes=%r.",
                self,
                school_classes,
                self.config.get("school_classes_keep_if_empty", False),
                self.school_classes,
            )
            self.school_classes = dict(
                (school, classes)
                for school, classes in iteritems(school_classes)
                if school in self.schools
            )
        if self.config["dry_run"]:
            self.logger.info("Dry-run: skipping user.modify() for %s.", self)
            return True
        else:
            return await super(ImportUser, self).modify_without_hooks(lo, validate, move_if_necessary)

    async def move(self, lo: UDM, udm_obj: UdmObject = None, force: bool = False) -> bool:
        self.lo = lo
        await self.check_schools(lo)
        return await super(ImportUser, self).move(lo, udm_obj, force)

    async def move_without_hooks(self, lo: UDM, udm_obj: UdmObject = None, force: bool = False) -> bool:
        if self.config["dry_run"]:
            self.logger.info("Dry-run: skipping user.move() for %s.", self)
            return True
        else:
            return await super(ImportUser, self).move_without_hooks(lo, udm_obj, force)

    @classmethod
    def normalize(cls, s):  # type: (str) -> str
        """
        Normalize string (german umlauts etc)

        :param str s: str to normalize
        :return: normalized `s`
        :rtype: str
        """
        if isinstance(s, string_types):
            # univention.admin.property._replace() may return bytes now
            s: Union[bytes, str] = cls.prop._replace("<:umlauts>{}".format(s), {})
            if isinstance(s, bytes):
                s: str = s.decode("utf-8")
        return s

    def normalize_udm_properties(self):  # type: () -> None
        """
        Normalize data in `self.udm_properties`.
        """

        def normalize_recursive(item):
            if isinstance(item, dict):
                for k, v in item.items():
                    item[k] = normalize_recursive(v)
                return item
            elif isinstance(item, list):
                for part in item:
                    normalize_recursive(part)
                return item
            else:
                return ImportUser.normalize(item)

        for k, v in self.udm_properties.items():
            self.udm_properties[k] = normalize_recursive(v)

    def reactivate(self):  # type: () -> None
        """
        Reactivate a deactivated user account, reset the account expiry
        setting and purge timestamp. Run this only on existing users fetched
        from LDAP.
        """
        self.logger.info("Reactivating %s...", self)
        self.expiration_date = None
        self.disabled = False
        self.set_purge_timestamp("")

    async def remove(self, lo):  # type: (UDM) -> bool
        self.lo = lo
        return await super(ImportUser, self).remove(lo)

    async def remove_without_hooks(self, lo: UDM) -> bool:
        if self.config["dry_run"]:
            self.logger.info("Dry-run: skipping user.remove() for %s.", self)
            return True
        else:
            return await super(ImportUser, self).remove_without_hooks(lo)

    async def validate(
        self,
        lo: UDM,
        validate_unlikely_changes: bool = False,
        check_username: bool = False,
    ) -> None:
        """
        Runs self-tests in the following order:

        * check existence of mandatory_attributes
        * check uniqueness of record_uid in this import job
        * check uniqueness of username in this import job
        * check uniqueness of email (mailPrimaryAddress) in this import job
        * check that username is not empty
        * check maximum username length
        * check minimum password_length
        * check email has valid format
        * check birthday has valid format
        * check school_classes is a dict
        * check schools is a list
        * check format of entries in school_classes
        * check existence of schools in school and schools
        * check that a username is not already in use by another user

        :param lo: LDAP connection object
        :param bool validate_unlikely_changes: whether to create messages in self.warnings for changes
            to certain attributes
        :param bool check_username: if username and password checks should run
        :return: None
        :raises MissingMandatoryAttribute: ...
        :raises UniqueIdError: ...
        :raises NoUsername: ...
        :raises UsernameToLong: ...
        :raises BadPassword: ...
        :raises InvalidEmail: ...
        :raises InvalidBirthday: ...
        :raises InvalidSchoolClasses: ...
        :raises InvalidSchools: ...
        """
        skip_tests = self.config.get("skip_tests", [])

        # check `name` 1st: it must be set, or `dn` will be empty, leading to AttributeError in
        # `User.validate()`
        if check_username:
            if not self.name:
                raise MissingUid(
                    "No username was created.", entry_count=self.entry_count, import_user=self
                )

            if len(self.name) > self.username_max_length:
                raise UsernameToLong(
                    "Username '{}' is longer than allowed.".format(self.name),
                    entry_count=self.entry_count,
                    import_user=self,
                )

            if len(self.password or "") < self.config["password_length"]:
                raise BadPassword(
                    "Password is shorter than {} characters.".format(self.config["password_length"]),
                    entry_count=self.entry_count,
                    import_user=self,
                )

        await super(ImportUser, self).validate(lo, validate_unlikely_changes)

        _ma = None
        mandatory_attributes = {}
        for _ma in self.config["mandatory_attributes"]:
            try:
                mandatory_attributes[_ma] = self.udm_properties[_ma]
                continue
            except KeyError:
                pass
            try:
                mandatory_attributes[_ma] = getattr(self, _ma)
            except AttributeError:
                raise MissingMandatoryAttribute(
                    "Mandatory attribute {!r} does not exist.".format(_ma),
                    self.config["mandatory_attributes"],
                    entry_count=self.entry_count,
                    import_user=self,
                )
        for k, v in iteritems(mandatory_attributes):
            if v in ("", None):
                raise EmptyMandatoryAttribute(
                    "Mandatory attribute {!r} has empty value.".format(k), attr_name=k
                )

        # don't run uniqueness checks from within a post_move hook
        if not self.in_hook and UNIQUENESS not in skip_tests:
            if self._unique_ids["record_uid"].get(self.record_uid, self.dn) != self.dn:
                raise UniqueIdError(
                    "record_uid {!r} has already been used in this import by {!r}.".format(
                        self.record_uid, self._unique_ids["record_uid"][self.record_uid]
                    ),
                    entry_count=self.entry_count,
                    import_user=self,
                )
            self._unique_ids["record_uid"][self.record_uid] = self.dn

            if check_username:
                if self._unique_ids["name"].get(self.name, self.dn) != self.dn:
                    raise UniqueIdError(
                        "Username {!r} has already been used in this import by {!r}.".format(
                            self.name, self._unique_ids["record_uid"][self.name]
                        ),
                        entry_count=self.entry_count,
                        import_user=self,
                    )
                self._unique_ids["name"][self.name] = self.dn

            if self.email:
                if self._unique_ids["email"].get(self.email, self.dn) != self.dn:
                    raise UniqueIdError(
                        "Email address {!r} has already been used in this import by {!r}.".format(
                            self.email, self._unique_ids["email"][self.email]
                        ),
                        entry_count=self.entry_count,
                        import_user=self,
                    )
                self._unique_ids["email"][self.email] = self.dn

        if self.email:
            # email_pattern:
            # * must not begin with an @
            # * must have >=1 '@' (yes, more than 1 is allowed)
            # * domain must contain dot
            # * all characters are allowed (international domains)
            email_pattern = r"[^@]+@.+\..+"
            if not re.match(email_pattern, self.email):
                raise InvalidEmail(
                    "Email address '{}' has invalid format.".format(self.email),
                    entry_count=self.entry_count,
                    import_user=self,
                )

        if self.birthday:
            try:
                datetime.datetime.strptime(self.birthday, "%Y-%m-%d")
            except (TypeError, ValueError) as exc:
                raise InvalidBirthday(
                    "Birthday has invalid format: {!r} error: {}.".format(self.birthday, exc),
                    entry_count=self.entry_count,
                    import_user=self,
                )

        if not isinstance(self.school_classes, dict):
            raise InvalidSchoolClasses(
                "School_classes must be a dict.", entry_count=self.entry_count, import_user=self
            )

        if not isinstance(self.schools, list):
            raise InvalidSchools(
                "Schools must be a list.", entry_count=self.entry_count, import_user=self
            )

        for school, school_classes in self.school_classes.items():
            for sc in school_classes:
                if sc.startswith("{0}-{0}-".format(school)):
                    self.logger.warning(
                        "Validation warning: Name of school_class starts with name of school: %r", sc
                    )
                for school_class in school_classes:
                    if not gid_syntax.regex.match(school_class):
                        raise InvalidSchoolClasses(
                            "Invalid school class name: {!r}".format(school_class),
                            entry_count=self.entry_count,
                            import_user=self,
                        )

        await self.check_schools(lo)

        if UNIQUENESS not in skip_tests:
            if not self._all_usernames:
                # fetch usernames of all users only once per import job
                # its faster to filter out computer names in Python than in LDAP
                # (and we have to loop over the query result anyway)
                self.__class__._all_usernames = dict(
                    (
                        attr["uid"][0],
                        UsernameUniquenessTuple(
                            attr.get("ucsschoolRecordUID", [None])[0],
                            attr.get("ucsschoolSourceUID", [None])[0],
                            dn,
                        ),
                    )
                    for dn, attr in self.ldap_lo_ro.search(
                        "objectClass=posixAccount",
                        attr=["uid", "ucsschoolRecordUID", "ucsschoolSourceUID"],
                    )
                    if not attr["uid"][0].endswith("$")
                )
            self._check_username_uniqueness()

    def _check_username_uniqueness(self):  # type: () -> None
        """
        Check that :py:attr:`self.name` is not already in use by another user.

        :raises UniqueIdError: if username is already taken by another user
        """
        uut = self._all_usernames.get(self.name)
        if uut and (uut.record_uid != self.record_uid or uut.source_uid != self.source_uid):
            raise UniqueIdError(
                "Username {!r} is already in use by {!r} (source_uid: {!r}, record_uid: {!r}).".format(
                    self.name, uut.dn, uut.source_uid, uut.record_uid
                )
            )

    def set_purge_timestamp(self, ts):  # type: (str) -> None
        """
        Set the date at which the account whould be deleted by the
        `ucs-school-purge-expired-users` script. Caller must run modify().

        :param str ts: account deletion date "%Y-%m-%d" or ""
        :return: None
        """
        self._purge_ts = ts

    @property
    def role_sting(self):  # type: () -> str
        """
        Mapping from self.roles to string used in configuration.

        :return: one of `staff`, `student`, `teacher`, `teacher_and_staff`
        :rtype: str
        """
        if role_pupil in self.roles or role_student in self.roles:
            return "student"
        elif role_teacher in self.roles:
            if role_staff in self.roles:
                return "teacher_and_staff"
            else:
                return "teacher"
        else:
            return "staff"

    @property
    def school_classes_as_str(self):  # type: () -> str
        """
        Create a string representation of the `school_classes` attribute.

        :return: string representation of `school_classes` attribute
        :rtype: str
        """
        return ",".join(",".join(sc) for sc in self.school_classes.values())

    @property
    def unique_email_handler(self):  # type: () -> UsernameHandler
        key = self.config["dry_run"]
        if key not in self._unique_email_handler_cache:
            self._unique_email_handler_cache[key] = self.factory.make_unique_email_handler(
                dry_run=self.config["dry_run"]
            )
        return self._unique_email_handler_cache[key]

    @property
    def username_handler(self):  # type: () -> UsernameHandler
        key = (self.username_max_length, self.config["dry_run"])
        if key not in self._username_handler_cache:
            self._username_handler_cache[key] = self.factory.make_username_handler(
                self.username_max_length, self.config["dry_run"]
            )
        return self._username_handler_cache[key]

    @property
    def username_scheme(self):  # type: () -> str
        """
        Fetch scheme for username for role.

        :return: scheme for the role from configuration
        :rtype: str
        """
        try:
            scheme = self.config["scheme"]["username"][self.role_sting]
        except KeyError:
            try:
                scheme = self.config["scheme"]["username"]["default"]
            except KeyError:
                raise NoUsernameAtAll(
                    "Cannot find scheme to create username for role '{}' or 'default'.".format(
                        self.role_sting
                    ),
                    self.entry_count,
                    import_user=self,
                )
        # force transcription of german umlauts
        return "<:umlauts>{}".format(scheme)

    def solve_format_dependencies(self, prop_to_format: str, scheme: str, **kwargs) -> None:
        """
        Call make_*() methods required to create values for <properties> used
        in scheme.

        :param str prop_to_format: name of property for which the `scheme` is
        :param str scheme: scheme used to format `prop_to_format`
        :param dict kwargs: additional data to use for formatting
        :return: None
        """
        no_brackets = scheme
        props_used_in_scheme = [x[0] for x in self._prop_regex.findall(no_brackets) if x[0]]
        for prop_used_in_scheme in props_used_in_scheme:
            if (
                hasattr(self, prop_used_in_scheme)
                and getattr(self, prop_used_in_scheme)
                or self.udm_properties.get(prop_used_in_scheme)
                or prop_used_in_scheme in kwargs
                or prop_used_in_scheme == "username"
                and (self.name or self.udm_properties.get("username"))
            ):
                # property exists and has value
                continue
            if (
                prop_used_in_scheme not in self._prop_providers
                and prop_used_in_scheme not in self.udm_properties
                and prop_used_in_scheme not in self.config["scheme"]
            ):
                # nothing we can do
                raise InitialisationError(
                    "Cannot find data provider for dependency {!r} for formatting of property {!r} with "
                    "scheme {!r}.".format(prop_used_in_scheme, prop_to_format, scheme),
                    entry_count=self.entry_count,
                    import_user=self,
                )

            try:
                method_sig = FunctionSignature(self._prop_providers[prop_used_in_scheme], (), {})
            except KeyError:
                method_sig = FunctionSignature("make_udm_property", (prop_used_in_scheme,), {})
            if method_sig in self._used_methods[prop_to_format]:
                # already ran make_<method_name>() for his formatting job
                self.logger.error(
                    "Tried running %s(%r, %r), although it has already run for %r.",
                    method_sig.name,
                    method_sig.args,
                    method_sig.kwargs,
                    prop_to_format,
                )
                raise InitialisationError(
                    "Recursion detected when resolving formatting dependencies for {!r}.".format(
                        prop_to_format
                    ),
                    entry_count=self.entry_count,
                    import_user=self,
                )
            self._used_methods[prop_to_format].append(method_sig)
            getattr(self, method_sig.name)(*method_sig.args, **method_sig.kwargs)
        self._used_methods.pop(prop_to_format, None)

    def format_from_scheme(self, prop_name, scheme, **kwargs):  # type: (str, str, **str) -> str
        """
        Format property with scheme for current import_user.
        * Uses the replacement code from users:templates.
        * This does not do the counter variable replacements for username.
        * Replacement <variables> are filled in the following oder (later
        additions overwriting previous ones):
        - from raw input data
        - from Attributes of self (ImportUser & ucsschool.lib.models.user.User)
        - from self.udm_properties
        - from kwargs

        :param str prop_name: name of property to be formatted
        :param str scheme: scheme to use
        :param dict kwargs: additional data to use for formatting
        :return: formatted string
        :rtype: str
        """
        from ..reader.base_reader import BaseReader  # isort:skip  # prevent cyclic import

        self.solve_format_dependencies(prop_name, scheme, **kwargs)
        if self.input_data:
            self.reader = cast(BaseReader, self.reader)
            all_fields = self.reader.get_data_mapping(self.input_data)
        else:
            all_fields = dict()
        all_fields.update(self.to_dict())
        all_fields.update(self.udm_properties)
        if "username" not in all_fields:
            all_fields["username"] = all_fields["name"]
        all_fields.update(kwargs)
        all_fields = self.call_format_hook(prop_name, all_fields)

        res: Union[bytes, str] = self.prop._replace(scheme, all_fields)
        # univention.admin.property._replace() may return bytes now
        if isinstance(res, bytes):
            res: str = res.decode("utf-8")
        if not res:
            self.logger.warning(
                "Created empty '{prop_name}' from scheme '{scheme}' and input data {data}. ".format(
                    prop_name=prop_name, scheme=scheme, data=all_fields
                )
            )
        return res

    @classmethod
    async def get_class_for_udm_obj(
        cls, udm_obj: UdmObject, school: str
    ) -> Union[None, Type["ImportUser"]]:
        """
        IMPLEMENTME if you subclass!
        """
        klass = await super(ImportUser, cls).get_class_for_udm_obj(udm_obj, school)
        if issubclass(klass, TeachersAndStaff):
            return ImportTeachersAndStaff
        elif issubclass(klass, Teacher):
            return ImportTeacher
        elif issubclass(klass, Staff):
            return ImportStaff
        elif issubclass(klass, Student):
            return ImportStudent
        else:
            return None

    def get_school_class_objs(self):  # type: () -> List[School]
        if isinstance(self.school_classes, string_types):
            # school_classes was set from input data
            self.make_classes()
        return super(ImportUser, self).get_school_class_objs()

    def _prevent_mapped_attributes_in_udm_properties(self):  # type: () -> None
        """
        Make sure users do not store values for ucsschool.lib mapped Attributes
        in udm_properties.
        """
        super(ImportUser, self)._prevent_mapped_attributes_in_udm_properties()
        if "e-mail" in self.udm_properties.keys() and not self.email:
            # this might be an mistake, so let's warn the user
            self.logger.warning(
                "UDM property 'e-mail' is used for storing contact information. The users mailbox "
                "address is stored in  the 'email' attribute of the {} object (not in "
                "udm_properties).".format(self.__class__.__name__)
            )

    def _schema_write_check(self, scheme_attr: str, ucsschool_attr: str, ldap_attr: str) -> bool:
        return scheme_attr in self.config["scheme"] and (
            not getattr(self.old_user, ucsschool_attr, None)
            or ldap_attr not in self.no_overwrite_attributes
        )

    def to_dict(self):  # type: () -> Dict[str, Any]
        res = super(ImportUser, self).to_dict()
        for attr in self._additional_props:
            res[attr] = getattr(self, attr)
        return res

    def update(self, other):  # type: (ImportUser) -> None
        """
        Copy attributes of other ImportUser into this one.

        IMPLEMENTME if you subclass and add attributes that are not
        ucsschool.lib.models.attributes.

        :param ImportUser other: data source
        """
        for k, v in other.to_dict().items():
            if k in self._additional_props and not v:
                continue
            setattr(self, k, v)

    @property
    def username_max_length(self):  # type: () -> int
        try:
            return self.config["username"]["max_length"][self.role_sting]
        except KeyError:
            return self.config["username"]["max_length"]["default"]

    @classmethod
    def school_classes_invalid_character_replacement(
        cls, school_class: str, char_replacement: str
    ) -> str:
        """
        Replace disallowed characters in ``school_class`` with ``char_replacement``. Allowed chars:
        ``[string.digits, string.ascii_letters, " -._"]``. If ``char_replacement`` is empty no
        replacement will be done.

        :param str school_class: name of school class
        :param str char_replacement: character to replace disallowed characters with
        :return: (possibly modified) name of school class
        :rtype: str
        """
        if not char_replacement or not school_class:
            return school_class
        klass_name_old = school_class  # for debug output at the end
        if isinstance(school_class, bytes):
            school_class = school_class.decode("utf-8")
        for character in school_class:
            if character not in ALLOWED_CHARS_IN_SCHOOL_CLASS_NAME:
                school_class = school_class.replace(character, char_replacement)
        if school_class != klass_name_old:
            cls.logger.debug("Class name changed from %r to %r.", klass_name_old, school_class)
        return school_class


class ImportStaff(ImportUser, Staff):
    pass


class ImportStudent(ImportUser, Student):
    pass


class ImportTeacher(ImportUser, Teacher):
    pass


class ImportTeachersAndStaff(ImportUser, TeachersAndStaff):
    pass


ConcreteImportUserClass = TypeVar(
    "ConcreteImportUserClass", ImportStaff, ImportStudent, ImportTeacher, ImportTeachersAndStaff
)


class ImportUserTypeConverter(UserTypeConverter):
    @classmethod
    async def convert(
        cls,
        user: ConcreteUserClass,
        new_cls: Type[ConcreteImportUserClass],
        udm: UDM,
        additional_classes: Dict[str, List[str]] = None,
    ) -> ConcreteImportUserClass:
        if not isinstance(user, ImportUser) or user.__class__ is ImportUser:
            raise TypeError(f"Argument 'user' is not an object of a 'ImportUser' subclass: {user!r}")
        if new_cls is ImportUser or not issubclass(new_cls, ImportUser):
            raise TypeError(f"Argument 'new_cls' is not a subclass of 'ImportUser': {new_cls!r}")
        return await super(ImportUserTypeConverter, cls).convert(user, new_cls, udm, additional_classes)

    @staticmethod
    def _dump_user_data(udm_user: UdmObject) -> str:
        res = super(ImportUserTypeConverter, ImportUserTypeConverter)._dump_user_data(udm_user)
        record_uid = udm_user.props.ucsschoolRecordUID
        source_uid = udm_user.props.ucsschoolSourceUID
        return f"{res} record_uid: {record_uid!r} source_uid: {source_uid!r}"


async def convert_to_staff(
    user: ConcreteUserClass,
    udm: UDM,
    additional_classes: Dict[str, List[str]] = None,
) -> ImportStaff:
    return await ImportUserTypeConverter.convert(user, ImportStaff, udm, additional_classes)


async def convert_to_student(
    user: ConcreteUserClass,
    udm: UDM,
    additional_classes: Dict[str, List[str]] = None,
) -> ImportStudent:
    return await ImportUserTypeConverter.convert(user, ImportStudent, udm, additional_classes)


async def convert_to_teacher(
    user: ConcreteUserClass,
    udm: UDM,
    additional_classes: Dict[str, List[str]] = None,
) -> ImportTeacher:
    return await ImportUserTypeConverter.convert(user, ImportTeacher, udm, additional_classes)


async def convert_to_teacher_and_staff(
    user: ConcreteUserClass,
    udm: UDM,
    additional_classes: Dict[str, List[str]] = None,
) -> ImportTeachersAndStaff:
    return await ImportUserTypeConverter.convert(user, ImportTeachersAndStaff, udm, additional_classes)
