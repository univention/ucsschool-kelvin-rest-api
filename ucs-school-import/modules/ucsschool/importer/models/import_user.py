# -*- coding: utf-8 -*-
#
# Univention UCS@school
"""
Representation of a user read from a file.
"""
# Copyright 2016 Univention GmbH
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

import random
import re
import string
import datetime
from collections import defaultdict
from ldap.filter import filter_format

from univention.admin.uexceptions import noObject
from univention.admin import property as uadmin_property
from ucsschool.lib.roles import role_pupil, role_teacher, role_staff
from ucsschool.lib.models import Staff, Student, Teacher, TeachersAndStaff, User
from ucsschool.lib.models.attributes import RecordUID, SourceUID
from ucsschool.importer.configuration import Configuration
from ucsschool.importer.factory import Factory
from ucsschool.importer.exceptions import BadPassword, FormatError, InvalidBirthday, InvalidClassName, InvalidEmail, MissingMailDomain, MissingMandatoryAttribute, MissingSchoolName, NotSupportedError, NoUsername, NoUsernameAtAll, UniqueIdError, UnkownDisabledSetting, UnknownProperty, UsernameToLong


class ImportUser(User):
	"""
	Representation of a user read from a file. Abstract class, please use one
	of its subclasses ImportStaff etc.

	An import profile and a factory must have been loaded, before the class
	can be used:

	from ucsschool.importer.configuration import Configuration
	from ucsschool.importer.factory import Factory, load_class
	config = Configuration("/usr/share/ucs-school-import/config_default.json")
	fac_class = load_class(config["factory"])
	factory = Factory(fac_class())
	user = factory.make_import_user(roles)
	"""
	source_uid = SourceUID("SourceUID")
	record_uid = RecordUID("RecordUID")

	config = None
	username_max_length = 15
	_unique_ids = defaultdict(set)
	factory = None
	ucr = None
	username_handler = None
	reader = None

	def __init__(self, name=None, school=None, **kwargs):
		self.action = None            # "A", "D" or "M"
		self.entry_count = 0          # line/node number of input data
		self.udm_properties = dict()  # UDM properties that are not stored in Attributes
		self.input_data = None        # raw input data created by SomeReader.read()
		if not self.factory:
			self.factory = Factory()
			self.ucr = self.factory.make_ucr()
			self.config = Configuration()
			self.reader = self.factory.make_reader()
		super(ImportUser, self).__init__(name, school, **kwargs)

	def build_hook_line(self, hook_time, func_name):
		"""
		Recreate original input data for hook creation.

		IMPLEMENTME if the Reader class in use does not put a list with the
		original input text in self.input_data. return _build_hook_line() with
		a list as argument.
		"""
		return self._build_hook_line(*self.input_data)

	@classmethod
	def get_by_import_id(cls, connection, source_uid, record_uid, superordinate=None):
		"""
		Retrieve an ImportUser.

		:param connection: uldap object
		:param source_uid: str: source DB identifier
		:param record_uid: str: source record identifier
		:param superordinate: str: superordinate
		:return: object of ImportUser subclass from LDAP or raises noObject
		"""
		filter_s = filter_format("(&(objectClass=ucsschoolType)(ucsschoolSourceUID=%s)(ucsschoolRecordUID=%s))",
			(source_uid, record_uid))
		obj = cls.get_only_udm_obj(connection, filter_s, superordinate=superordinate)
		if not obj:
			raise noObject("No user with source_uid={0} and record_uid={1} found.".format(source_uid, record_uid))
		return cls.from_udm_obj(obj, None, connection)

	def deactivate(self):
		"""
		Deactivate user account. Caller must run modify().
		"""
		self.disabled = "all"

	def expire(self, connection, expiry):
		"""
		Set the account expiration date.

		:param connection: uldap connection object
		:param expiry: str: expire date "%Y-%m-%d" or ""
		"""
		user_udm = self.get_udm_object(connection)
		user_udm["userexpiry"] = expiry
		user_udm.modify()
		# This operation partly invalidates the cached ucsschool.lib User:
		# setting the 'disabled' attribute after this would raise an ldapError.
		# Invalidating cache:
		self._udm_obj_searched = False

	def has_expired(self, connection):
		"""
		Check if the user account has expired.

		:param connection: uldap connection object
		:return: bool: whether the user account has expired
		"""
		user_udm = self.get_udm_object(connection)
		if not user_udm["userexpiry"]:
			return False
		expiry = datetime.datetime.strptime(user_udm["userexpiry"], "%Y-%m-%d")
		return datetime.datetime.now() > expiry

	def has_expiry(self, connection):
		"""
		Check if the user account has an expiry date set (regardless if it is
		in the future or past).

		:param connection: uldap connection object
		:return: bool: whether the user account has an expiry date set
		"""
		user_udm = self.get_udm_object(connection)
		return bool(user_udm["userexpiry"])

	def prepare_all(self, new_user=False):
		"""
		Necessary preparation to modify a user in UCS.
		Runs all make_* functions.

		:param new_user: bool: if username and password should be created
		"""
		self.prepare_uids()
		self.prepare_udm_properties()
		self.prepare_attributes(new_user)
		self.run_checks(check_username=new_user)

	def prepare_attributes(self, new_user=False):
		"""
		Run make_* functions for all Attributes of ucsschool.lib.models.user.User.
		:param new_user:
		:return:
		"""
		self.make_firstname()
		self.make_lastname()
		self.make_school()
		self.make_schools()
		self.make_username()
		if new_user:
			self.make_password()
		if self.password:
			self.udm_properties["overridePWHistory"] = "1"
			self.udm_properties["overridePWLength"] = "1"
		self.make_classes()
		self.make_birthday()
		self.make_disabled()
		self.make_email()

	def prepare_udm_properties(self):
		"""
		Create self.udm_properties from schemes configured in config["scheme"].
		Existing entries will be overwritten!

		* Attributes (email, rid, [user]name etc.) are ignored, as they are
		processed separately in make_*.
		* See /usr/share/doc/ucs-school-import/user_import_configuration_readme.txt.gz
		section "scheme" for details on the configuration.
		"""
		ignore_keys = self.to_dict().keys()
		ignore_keys.extend(["mailPrimaryAddress", "rid", "username"])
		for k, v in self.config["scheme"].items():
			if k in ignore_keys:
				continue
			self.udm_properties[k] = self.format_from_scheme(k, v)

	def prepare_uids(self):
		"""
		Necessary preparation to detect if user exists in UCS.
		Runs make_* functions for record_uid and source_uid Attributes of
		ImportUser.
		"""
		self.make_rid()
		self.make_sid()

	def make_birthday(self):
		"""
		Set User.birthday attribute.
		"""
		if "birthday" in self.config["scheme"]:
			self.birthday = self.format_from_scheme("birthday", self.config["scheme"]["birthday"])

	def make_classes(self):
		"""
		Create school classes.

		* This should run after make_school().
		* If attribute already exists as a dict, it is not changed.
		* Attribute is only written if it is set to a string like
		'school1-cls2,school3-cls4'.
		"""
		if isinstance(self, Staff):
			self.school_classes = dict()
		elif self.school_classes and isinstance(self.school_classes, dict):
			return
		elif self.school_classes and isinstance(self.school_classes, basestring):
			res = defaultdict(list)
			for a_class in self.school_classes.strip(",").split(","):
				school, sep, cls_name = a_class.partition("-")
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
				res[school].append("{}-{}".format(school, cls_name))
			self.school_classes = dict(res)
		else:
			raise RuntimeError("Unknown data in attribute 'school_classes': '{}'".format(self.school_classes))

	def make_disabled(self):
		"""
		Set User.disabled attribute.
		"""
		if self.disabled is not None:
			return

		try:
			activate = self.config["activate_new_users"][self.role_sting]
		except KeyError:
			try:
				activate = self.config["activate_new_users"]["default"]
			except KeyError:
				raise UnkownDisabledSetting("Cannot find 'disabled' ('activate_new_users') setting for role '{}' or "
					"'default'.".format(self.role_sting), self.entry_count, import_user=self)
		self.disabled = "none" if activate else "all"

	def make_firstname(self):
		"""
		Normalize given name if set from import data or create from scheme.
		"""
		if self.firstname:
			self.firstname = self.normalize(self.firstname)
		elif "firstname" in self.config["scheme"]:
			self.firstname = self.format_from_scheme("firstname", self.config["scheme"]["firstname"])
		else:
			self.firstname = ""

	def make_lastname(self):
		"""
		Normalize family name if set from import data or create from scheme.
		"""
		if self.lastname:
			self.lastname = self.normalize(self.lastname)
		elif "lastname" in self.config["scheme"]:
			self.lastname = self.format_from_scheme("lastname", self.config["scheme"]["lastname"])
		else:
			self.lastname = ""

	def make_email(self):
		"""
		Create email from scheme (if not already set).

		If any of the other attributes is used in the format scheme of the
		email address, its make_* function should have run before this!
		"""
		if self.email:
			return
		try:
			self.email = self.udm_properties.pop("mailPrimaryAddress")
			return
		except KeyError:
			pass

		maildomain = self.config.get("maildomain")
		if not maildomain:
			try:
				maildomain = self.ucr["mail/hosteddomains"].split()[0]
			except (AttributeError, IndexError):
				raise MissingMailDomain("Could not retrieve mail domain from configuration nor from UCRV "
					"mail/hosteddomains.", entry=self.entry_count, import_user=self)
		self.email = self.format_from_scheme("email", self.config["scheme"]["email"], maildomain=maildomain).lower()

	def make_password(self):
		"""
		Create random password (if not already set).
		"""
		if not self.password:
			pw = list(random.choice(string.lowercase))
			pw.append(random.choice(string.uppercase))
			pw.append(random.choice(string.digits))
			pw.append(random.choice(u"@#$%^&*-_+=[]{}|\:,.?/`~();"))
			pw.extend(random.choice(string.ascii_letters + string.digits + u"@#$%^&*-_+=[]{}|\:,.?/`~();")
				for _ in range(self.config["password_length"] - 4))
			random.shuffle(pw)
			self.password = u"".join(pw)

	def make_rid(self):
		"""
		Create ucsschoolRecordUID (rid) (if not already set).
		"""
		if not self.record_uid:
			self.record_uid = self.format_from_scheme("rid", self.config["scheme"]["rid"])

	def make_sid(self):
		"""
		Set the ucsschoolSourceUID (sid) (if not already set).
		"""
		if self.source_uid:
			if self.source_uid != self.config["sourceUID"]:
				raise NotSupportedError("Source_uid '{}' differs to configured source_uid '{}'.".format(
					self.source_uid, self.config["sourceUID"]))
		else:
			self.source_uid = self.config["sourceUID"]

	def make_school(self):
		"""
		Create 'school' attribute - the position of the object in LDAP (if not already set).

		Order of detection:
		* already set (object creation or reading from input)
		* from configuration (file or cmdline)
		* first (alphanum-sorted) school in attribute schools
		"""
		if self.school:
			self.school = self.normalize(self.school)
		elif self.config.get("school"):
			self.school = self.config["school"]
		elif self.schools and isinstance(self.schools, list):
			self.school = self.normalize(sorted(self.schools)[0])
		elif self.schools and isinstance(self.schools, basestring):
			self.make_schools()  # this will recurse back, but schools will be a list then
		else:
			raise MissingSchoolName("Primary school name (ou) was not set on the cmdline or in the configuration file "
				"and was not found in the input data.", entry=self.entry_count, import_user=self)

	def make_schools(self):
		"""
		Create list of schools this user is in.
		If possible, this should run after make_school()

		* If empty, it is set to self.school.
		* If it is a string like 'school1,school2,school3' the attribute is
		created from it.
		"""
		if self.schools and isinstance(self.schools, list):
			pass
		elif not self.schools:
			if not self.school:
				self.make_school()
			self.schools = [self.school]
		elif isinstance(self.schools, basestring):
			self.schools = self.schools.strip(",").split(",")
			self.schools = sorted([self.normalize(s.strip()) for s in self.schools])
		else:
			raise RuntimeError("Unknown data in attribute 'schools': '{}'".format(self.schools))

		if not self.school:
			self.make_school()
		if self.school not in self.schools:
			if not self.schools:
				self.schools = [self.school]
			else:
				self.school = sorted(self.schools)[0]

	def make_username(self):
		"""
		Create username if not already set in self.name or self.udm_properties["username"].
		[ALWAYSCOUNTER] and [COUNTER2] are supported, but only one may be used
		per name.
		"""
		if self.name:
			return
		try:
			self.name = self.udm_properties.pop("username")
			return
		except KeyError:
			pass

		self.name = self.format_from_scheme("username", self.username_scheme)
		if not self.name:
			raise FormatError("No username was created from scheme '{}'.".format(self.username_scheme))
		if not self.username_handler:
			self.username_handler = self.factory.make_username_handler(self.username_max_length)
		self.name = self.username_handler.format_username(self.name)

	@staticmethod
	def normalize(s):
		"""
		Normalize string (german umlauts etc)

		:param s: str
		:return: str: normalized s
		"""
		if isinstance(s, basestring):
			prop = uadmin_property("_replace")
			s = prop._replace("<:umlauts>{}".format(s), {})
		return s

	def normalize_udm_properties(self):
		"""
		Normalize data in self.udm_properties.
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

	def reactivate(self, connection):
		"""
		Reactivate a deactivated user account and reset the account expiry
		setting. Run this only on existing users fetched from LDAP.

		:param connection: uldap connection object
		"""
		self.expire(connection, "")
		self.disabled = "none"

	def run_checks(self, check_username=False):
		"""
		Run some self-tests.

		:param check_username: bool: if username and password checks should run
		"""
		try:
			[self.udm_properties.get(ma) or getattr(self, ma) for ma in self.config["mandatory_attributes"]]
		except (AttributeError, KeyError) as exc:
			raise MissingMandatoryAttribute("A mandatory attribute was not set: {}.".format(exc),
				self.config["mandatory_attributes"], entry=self.entry_count, import_user=self)


		if self.record_uid in self._unique_ids["rid"]:
			raise UniqueIdError("RecordUID '{}' has already been used in this import.".format(self.record_uid),
				entry=self.entry_count, import_user=self)
		self._unique_ids["rid"].add(self.record_uid)

		if check_username:
			if not self.name:
				raise NoUsername("No username was created.", entry=self.entry_count, import_user=self)

			if len(self.name) > self.username_max_length:
				raise UsernameToLong("Username '{}' is longer than allowed.".format(self.name),
					entry=self.entry_count, import_user=self)

			if self.name in self._unique_ids["name"]:
				raise UniqueIdError("Username '{}' has already been used in this import.".format(self.name),
					entry=self.entry_count, import_user=self)
			self._unique_ids["name"].add(self.name)

			if len(self.password) < self.config["password_length"]:
				raise BadPassword("Password is shorter than {} characters.".format(self.config["password_length"]),
					entry=self.entry_count, import_user=self)

		if self.email:
			# email_pattern:
			# * must not begin with an @
			# * must have >=1 '@' (yes, more than 1 is allowed)
			# * domain must contain dot
			# * all characters are allowed (international domains)
			email_pattern = r"[^@]+@.+\..+"
			if not re.match(email_pattern, self.email):
				raise InvalidEmail("Email address '{}' has invalid format.".format(self.email), entry=self.entry_count,
					import_user=self)

			if self.email in self._unique_ids["email"]:
				raise UniqueIdError("Email address '{}' has already been used in this import.".format(self.email),
					entry=self.entry_count, import_user=self)
			self._unique_ids["email"].add(self.email)

		if self.birthday:
			try:
				self.birthday = datetime.datetime.strptime(self.birthday, "%Y-%m-%d").isoformat()
			except ValueError as exc:
				raise InvalidBirthday("Birthday has invalid format: {}.".format(exc), entry=self.entry_count,
					import_user=self)

	@property
	def role_sting(self):
		"""
		Mapping from self.roles to string used in configuration.

		:return: str: one of staff, student, teacher, teacher_and_staff
		"""
		if role_pupil in self.roles:
			return "student"
		elif role_teacher in self.roles:
			if role_staff in self.roles:
				return "teacher_and_staff"
			else:
				return "teacher"
		else:
			return "staff"

	@property
	def username_scheme(self):
		"""
		Fetch scheme for username for role.

		:return: str: scheme for the role from configuration
		"""
		try:
			scheme = unicode(self.config["scheme"]["username"][self.role_sting])
		except KeyError:
			try:
				scheme = unicode(self.config["scheme"]["username"]["default"])
			except KeyError:
				raise NoUsernameAtAll("Cannot find scheme to create username for role '{}' or 'default'.".format(
					self.role_sting), self.entry_count, import_user=self)
		# force transcription of german umlauts
		return "<:umlauts>{}".format(scheme)

	def format_from_scheme(self, prop_name, scheme, **kwargs):
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

		:param prop_name: str: name of property (for error logging)
		:param scheme: str: scheme to use
		:param kwargs: dict: additional data to use for formatting
		:return: str: formatted string
		"""
		if self.input_data:
			all_fields = self.reader.get_data_mapping(self.input_data)
		else:
			all_fields = dict()
		all_fields.update(self.to_dict().copy())
		all_fields.update(self.udm_properties)
		all_fields.update(kwargs)

		prop = uadmin_property("_replace")
		res = prop._replace(scheme, all_fields)
		if not res:
			raise FormatError("Could not create '{prop_name}' from scheme '{scheme}' and input data {data}. ".format(
				prop_name=prop_name, scheme=scheme, data=all_fields), scheme=scheme, data=all_fields,
				entry=self.entry_count,	import_user=self)
		return res

	@classmethod
	def get_class_for_udm_obj(cls, udm_obj, school):
		"""
		IMPLEMENTME if you subclass!
		"""
		klass = super(ImportUser, cls).get_class_for_udm_obj(udm_obj, school)
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

	def get_school_class_objs(self):
		if isinstance(self.school_classes, basestring):
			# school_classes was set from input data
			self.make_classes()
		return super(ImportUser, self).get_school_class_objs()

	def create_without_hooks(self, lo, validate):
		success = super(ImportUser, self).create_without_hooks(lo, validate)
		self.store_udm_properties(lo)
		return success

	def modify_without_hooks(self, lo, validate=True, move_if_necessary=None):
		# must set udm_properties first, as they contain overridePWHistory and
		# overridePWLength
		self.store_udm_properties(lo)
		success = super(ImportUser, self).modify_without_hooks(lo, validate, move_if_necessary)
		return success

	def store_udm_properties(self, connection):
		"""
		Copy data from self.udm_properties into UDM object of this user.

		:param connection: LDAP connection
		"""
		if not self.udm_properties:
			return
		udm_obj = self.get_udm_object(connection)
		udm_obj.info.update(self.udm_properties)
		try:
			udm_obj.modify()
		except KeyError as exc:
			raise UnknownProperty("UDM properties could not be set. Unknown property: '{}'".format(exc),
				entry=self.entry_count, import_user=self)

	def update(self, other):
		"""
		Copy attributes of other ImportUser into this one.

		IMPLEMENTME if you subclass and add attributes that are not
		ucsschool.lib.models.attributes.
		:param other: ImportUser: data source
		"""
		for k, v in other.to_dict().items():
			if k == "name" and v is None:
				continue
			setattr(self, k, v)
		self.action = other.action
		self.entry_count = other.entry_count
		self.udm_properties.update(other.udm_properties)
		self.input_data = other.input_data


class ImportStaff(ImportUser, Staff):
	pass


class ImportStudent(ImportUser, Student):
	pass


class ImportTeacher(ImportUser, Teacher):
	pass


class ImportTeachersAndStaff(ImportUser, TeachersAndStaff):
	pass