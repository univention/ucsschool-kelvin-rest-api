#!/usr/bin/python2.7
# -*- coding: utf-8 -*-
#
# UCS@school python lib: models
#
# Copyright 2014-2018 Univention GmbH
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

import os.path
from copy import deepcopy
import tempfile
import subprocess

import ldap
from ldap import explode_dn
from ldap.filter import escape_filter_chars
from ldap.dn import escape_dn_chars

import univention.admin.uldap as udm_uldap
from univention.admin.uexceptions import noObject
import univention.admin.modules as udm_modules
import univention.admin.objects as udm_objects
from univention.admin.filter import conjunction, expression
from univention.management.console.modules.sanitizers import LDAPSearchSanitizer

from ucsschool.lib.schoolldap import SchoolSearchBase, LDAP_Connection
from ucsschool.lib.models.meta import UCSSchoolHelperMetaClass
from ucsschool.lib.models.attributes import CommonName, SchoolAttribute, ValidationError
from ucsschool.lib.models.utils import ucr, _, logger


class NoObject(noObject):
	pass


class UnknownModel(NoObject):

	def __init__(self, dn, cls):
		self.dn = dn
		self.wrong_model = cls
		super(UnknownModel, self).__init__('No python class: %r is not a %s' % (dn, cls.__name__))


class WrongModel(NoObject):

	def __init__(self, dn, model, wrong_model):
		self.dn = dn
		self.model = model
		self.wrong_model = wrong_model
		super(WrongModel, self).__init__('Wrong python class: %r is not a %r but a %r' % (dn, wrong_model.__name__, model.__name__))


class WrongObjectType(NoObject):

	def __init__(self, dn, cls):
		self.dn = dn
		self.wrong_model = cls
		super(WrongObjectType, self).__init__('Wrong objectClass: %r is not a %r.' % (dn, cls.__name__))


class MultipleObjectsError(Exception):

	def __init__(self, objs, *args, **kwargs):
		super(MultipleObjectsError, self).__init__(*args, **kwargs)
		self.objs = objs


class UCSSchoolHelperAbstractClass(object):
	'''
	Base class of all UCS@school models.
	Hides UDM.

	Attributes used for a class are defined like this:

	class MyModel(UCSSchoolHelperAbstractClass):
		my_attribute = Attribute('Label', required=True, udm_name='myAttr')

	From there on my_attribute=value may be passed to __init__,
	my_model.my_attribute can be accessed and the value will be saved
	as obj['myAttr'] in UDM when saving this instance.
	If an attribute of a base class is not wanted, it can be overridden:

	class MyModel(UCSSchoolHelperAbstractClass):
		school = None

	Meta information about the class are defined like this:
	class MyModel(UCSSchoolHelperAbstractClass):
		class Meta:
			udm_module = 'my/model'

	The meta information is then accessible in cls._meta

	Important functions:
		__init__(**kwargs):
			kwargs should be the defined attributes
		create(lo)
			lo is an LDAP connection, specifically univention.admin.access.
			creates a new object. Returns False is the object already exists.
			And True after the creation
		modify(lo)
			modifies an existing object. Returns False if the object does not
			exist and True after the modification (regardless whether something
			actually changed or not)
		remove(lo)
			deletes the object. Returns False if the object does not exist and True
			after the deletion.
		get_all(lo, school, filter_str, easy_filter=False)
			classmethod; retrieves all objects found for this school. filter can be a string
			that is used to narrow down a search. Each property of the class' udm_module
			that is include_in_default_search is queried for that string.
			Example:
			User.get_all(lo, 'school', filter_str='name', easy_filter=True)
			will search in cn=users,ou=school,$base
			for users/user UDM objects with |(username=*name*)(firstname=*name*)(...) and return
			User objects (not UDM objects)
			With easy_filter=False (default) it will use this very filter_str
		get_container(school)
			a classmethod that points to the container where new instances are created
			and existing ones are searched.
		dn
			property, current distinguishable name of the instance. Calculated on the fly, it
			changes if instance.name or instance.school changes.
			instance.old_dn will be set to the original dn when the instance was created
		get_udm_object(lo)
			searches UDM for an entry that corresponds to self. Normally uses the old_dn or dn.
			If cls._meta.name_is_unique then any object with self.name will match
		exists(lo)
			whether this object can be found in UDM.
		from_udm_obj(udm_obj, school, lo)
			classmethod; maps the info of udm_obj into a new instance (and sets school)
		from_dn(dn, school, lo)
			finds dn in LDAP and uses from_udm_obj
		get_first_udm_obj(lo, filter_str)
			returns the first found object of type cls._meta.udm_module that matches an
			arbitrary filter_str

	More features:
	* Validation:
		There are some auto checks built in: Attributes of the model that have a
		UDM syntax attached are validated against this syntax. Attributes that are
		required must be present.
		Attributes that are unlikely_to_change give a warning (not error) if the object
		already exists with other values.
		If the Meta information states that name_is_unique, the complete LDAP is searched
		for the instance's name before continuing.
		validate() can be further customized.
	* Hooks:
		Before create, modify, move and remove, hooks are called if build_hook_line()
		returns something. If the operation was successful, another set of hooks
		are called.
		All scripts in
		/usr/share/ucs-school-import/hooks/%(module)s_{create|modify|move|remove}_{pre|post}.d/
		are called with the name of a temporary file containing the hook_line via run-parts.
		%(module)s is 'ucc' for cls._meta.udm_module == 'computers/ucc' by default and
		can be explicitely set with
		class Meta:
			hook_path = 'computer'
	'''
	__metaclass__ = UCSSchoolHelperMetaClass
	_cache = {}

	_search_base_cache = {}
	_initialized_udm_modules = []
	_empty_hook_paths = set()

	hook_sep_char = '\t'
	hook_path = '/usr/share/ucs-school-import/hooks/'

	name = CommonName(_('Name'), aka=['Name'])
	school = SchoolAttribute(_('School'), aka=['School'])

	@classmethod
	def cache(cls, *args, **kwargs):
		'''Initializes a new instance and caches it for subsequent calls.
		Useful when using School.cache(school_name) a lot in different
		functions, in loops, etc.
		'''
		args = list(args)
		if args:
			kwargs['name'] = args.pop(0)
		if args:
			kwargs['school'] = args.pop(0)
		key = [cls.__name__] + [(k, kwargs[k]) for k in sorted(kwargs)]
		key = tuple(key)
		if key not in cls._cache:
			logger.debug('Initializing %r', key)
			obj = cls(**kwargs)
			cls._cache[key] = obj
		return cls._cache[key]

	@classmethod
	def invalidate_all_caches(cls):
		from ucsschool.lib.models.user import User
		from ucsschool.lib.models.network import Network
		from ucsschool.lib.models.utils import _pw_length_cache
		cls._cache.clear()
		# cls._search_base_cache.clear() # useless to clear
		_pw_length_cache.clear()
		Network._netmask_cache.clear()
		User._profile_path_cache.clear()
		User._samba_home_path_cache.clear()

	@classmethod
	def invalidate_cache(cls):
		for key in cls._cache.keys():
			if key[0] == cls.__name__:
				logger.debug('Invalidating %r', key)
				cls._cache.pop(key)

	@classmethod
	def supports_school(cls):
		return 'school' in cls._attributes

	def __init__(self, name=None, school=None, **kwargs):
		'''Initializes a new instance with kwargs.
		Not every kwarg is accepted, though: The name
		must be defined as a attribute at class level
		(or by a base class). All attributes are
		initialized at least with None
		Sets self.old_dn to self.dn, i.e. the name
		in __init__ will determine the old_dn, changing
		it after __init__ will result in trying to move the
		object!
		'''
		self._udm_obj_searched = False
		self._udm_obj = None
		kwargs['name'] = name
		kwargs['school'] = school
		for key, attr in self._attributes.items():
			default = attr.value_default
			if callable(default):
				default = default()
			setattr(self, key, kwargs.get(key, default))
		self.__position = None
		self.old_dn = None
		self.old_dn = self.dn
		self.errors = {}
		self.warnings = {}

	@classmethod
	@LDAP_Connection()
	def get_machine_connection(cls, ldap_user_read=None, ldap_machine_write=None):
		"""Shortcut to get a cached ldap connection to the DC Master using this host's credentials"""
		return ldap_machine_write

	@property
	def position(self):
		if self.__position is None:
			return self.get_own_container()
		return self.__position

	@position.setter
	def position(self, position):
		if self.position != position:  # allow dynamic school changes until creation
			self.__position = position

	@property
	def dn(self):
		'''Generates a DN where the lib would assume this
		instance to be. Changing name or school of self will most
		likely change the outcome of self.dn as well
		'''
		if self.name and self.position:
			name = self._meta.ldap_map_function(self.name)
			return '%s=%s,%s' % (self._meta.ldap_name_part, escape_dn_chars(name), self.position)
		return self.old_dn

	def set_dn(self, dn):
		'''Does not really set dn, as this is generated
		on-the-fly. Instead, sets old_dn in case it was
		missed in the beginning or after create/modify/remove/move
		Also resets cached udm_obj as it may point to somewhere else
		'''
		self._udm_obj_searched = False
		self.position = ldap.dn.dn2str(ldap.dn.str2dn(dn)[1:])
		self.old_dn = dn

	def validate(self, lo, validate_unlikely_changes=False):
		from ucsschool.lib.models.school import School
		self.errors.clear()
		self.warnings.clear()
		for name, attr in self._attributes.iteritems():
			value = getattr(self, name)
			try:
				attr.validate(value)
			except ValueError as e:
				self.add_error(name, str(e))
		if self._meta.name_is_unique and not self._meta.allow_school_change:
			if self.exists_outside_school(lo):
				self.add_error('name', _('The name is already used somewhere outside the school. It may not be taken twice and has to be changed.'))
		if self.supports_school() and self.school:
			if not School.cache(self.school).exists(lo):
				self.add_error('school', _('The school "%s" does not exist. Please choose an existing one or create it.') % self.school)
		if validate_unlikely_changes:
			if self.exists(lo):
				udm_obj = self.get_udm_object(lo)
				try:
					original_self = self.from_udm_obj(udm_obj, self.school, lo)
				except (UnknownModel, WrongModel):
					pass
				else:
					for name, attr in self._attributes.iteritems():
						if attr.unlikely_to_change:
							new_value = getattr(self, name)
							old_value = getattr(original_self, name)
							if new_value and old_value:
								if new_value != old_value:
									self.add_warning(name, _('The value changed from %(old)s. This seems unlikely.') % {'old': old_value})

	def add_warning(self, attribute, warning_message):
		warnings = self.warnings.setdefault(attribute, [])
		if warning_message not in warnings:
			warnings.append(warning_message)

	def add_error(self, attribute, error_message):
		errors = self.errors.setdefault(attribute, [])
		if error_message not in errors:
			errors.append(error_message)

	def exists(self, lo):
		return self.get_udm_object(lo) is not None

	def exists_outside_school(self, lo):
		if not self.supports_school():
			return False
		from ucsschool.lib.models.school import School
		udm_obj = self.get_udm_object(lo)
		if udm_obj is None:
			return False
		return not udm_obj.dn.endswith(School.cache(self.school).dn)

	def call_hooks(self, hook_time, func_name):
		'''Calls run-parts in
		os.path.join(self.hook_path, '%s_%s_%s.d' % (self._meta.hook_path, func_name, hook_time))
		if self.build_hook_line(hook_time, func_name) returns a non-empty string

		Usage in lib itself:
			hook_time in ['pre', 'post']
			func_name in ['create', 'modify', 'remove']

		In the lib, post-hooks are only called if the corresponding function returns True
		'''
		# verify path
		hook_path = self._meta.hook_path
		path = os.path.join(self.hook_path, '%s_%s_%s.d' % (hook_path, func_name, hook_time))
		if path in self._empty_hook_paths:
			return None
		if not os.path.isdir(path) or not os.listdir(path):
			logger.debug('%s not found or empty.', path)
			self._empty_hook_paths.add(path)
			return None
		logger.debug('%s shall be executed', path)

		dn = None
		if hook_time == 'post':
			dn = self.old_dn

		logger.debug('Building hook line: %r.build_hook_line(%r, %r)', self, hook_time, func_name)
		line = self.build_hook_line(hook_time, func_name)
		if not line:
			logger.debug('No line. Skipping!')
			return None
		line = line.strip() + '\n'

		# create temporary file with data
		with tempfile.NamedTemporaryFile() as tmpfile:
			tmpfile.write(line)
			tmpfile.flush()

			# invoke hook scripts
			# <script> <temporary file> [<ldap dn>]
			command = ['run-parts', path, '--arg', tmpfile.name]
			if dn:
				command.extend(('--arg', dn))

			ret_code = subprocess.call(command)

			return ret_code == 0

	def build_hook_line(self, hook_time, func_name):
		'''Must be overridden if the model wants to support hooks.
		Do so by something like:
		return self._build_hook_line(self.attr1, self.attr2, 'constant')
		'''
		return None

	def _alter_udm_obj(self, udm_obj):
		for name, attr in self._attributes.iteritems():
			if attr.udm_name:
				value = getattr(self, name)
				if value is not None:
					udm_obj[attr.udm_name] = value

	def create(self, lo, validate=True):
		'''
		Creates a new UDM instance.
		Calls pre-hooks.
		If the object already exists, returns False.
		If the object does not yet exist, creates it, returns True and
		calls post-hooks.
		'''
		self.call_hooks('pre', 'create')
		success = self.create_without_hooks(lo, validate)
		if success:
			self.call_hooks('post', 'create')
		return success

	def create_without_hooks(self, lo, validate):
		if self.exists(lo):
			return False
		logger.info('Creating %r', self)

		if validate:
			self.validate(lo)
			if self.errors:
				raise ValidationError(self.errors.copy())

		pos = udm_uldap.position(ucr.get('ldap/base'))
		container = self.position
		if not container:
			logger.error('%r cannot determine a container. Unable to create!', self)
			return False
		try:
			pos.setDn(container)
			udm_obj = udm_modules.get(self._meta.udm_module).object(None, lo, pos, superordinate=self.get_superordinate(lo))
			udm_obj.open()

			# here is the real logic
			self.do_create(udm_obj, lo)

			# get it fresh from the database (needed for udm_obj._exists ...)
			self.set_dn(self.dn)
			logger.info('%r successfully created', self)
			return True
		finally:
			self.invalidate_cache()

	def do_create(self, udm_obj, lo):
		'''Actual udm_obj manipulation. Override this if
		you want to further change values of udm_obj, e.g.
		def do_create(self, udm_obj, lo):
			udm_obj['used_in_ucs_school'] = '1'
			super(MyModel, self).do_create(udm_obj, lo)
		'''
		self._alter_udm_obj(udm_obj)
		udm_obj.create()

	def modify(self, lo, validate=True, move_if_necessary=None):
		'''
		Modifies an existing UDM instance.
		Calls pre-hooks.
		If the object does not exist, returns False.
		If the object exists, modifies it, returns True and
		calls post-hooks.
		'''
		self.call_hooks('pre', 'modify')
		success = self.modify_without_hooks(lo, validate, move_if_necessary)
		if success:
			self.call_hooks('post', 'modify')
		return success

	def modify_without_hooks(self, lo, validate=True, move_if_necessary=None):
		logger.info('Modifying %r', self)

		if move_if_necessary is None:
			move_if_necessary = self._meta.allow_school_change

		if validate:
			self.validate(lo, validate_unlikely_changes=True)
			if self.errors:
				raise ValidationError(self.errors.copy())

		udm_obj = self.get_udm_object(lo)
		if not udm_obj:
			logger.info('%s does not exist!', self.old_dn)
			return False

		try:
			old_attrs = deepcopy(udm_obj.info)
			self.do_modify(udm_obj, lo)
			# get it fresh from the database
			self.set_dn(self.dn)
			udm_obj = self.get_udm_object(lo)
			same = old_attrs == udm_obj.info
			if move_if_necessary:
				if udm_obj.dn != self.dn:
					if self.move_without_hooks(lo, udm_obj, force=True):
						same = False
			if same:
				logger.info('%r not modified. Nothing changed', self)
			else:
				logger.info('%r successfully modified', self)
			# return not same
			return True
		finally:
			self.invalidate_cache()

	def do_modify(self, udm_obj, lo):
		'''Actual udm_obj manipulation. Override this if
		you want to further change values of udm_obj, e.g.
		def do_modify(self, udm_obj, lo):
			udm_obj['used_in_ucs_school'] = '1'
			super(MyModel, self).do_modify(udm_obj, lo)
		'''
		self._alter_udm_obj(udm_obj)
		udm_obj.modify(ignore_license=1)

	def move(self, lo, udm_obj=None, force=False):
		self.call_hooks('pre', 'move')
		success = self.move_without_hooks(lo, udm_obj, force)
		if success:
			self.call_hooks('post', 'move')
		return success

	def move_without_hooks(self, lo, udm_obj, force=False):
		if udm_obj is None:
			udm_obj = self.get_udm_object(lo)
		if udm_obj is None:
			logger.warning('No UDM object found to move from (%r)', self)
			return False
		if self.supports_school() and self.get_school_obj(lo) is None:
			logger.warn('%r wants to move itself to a not existing school', self)
			return False
		logger.info('Moving %r to %r', udm_obj.dn, self)
		if udm_obj.dn == self.dn:
			logger.warning('%r wants to move to its own DN!', self)
			return False
		if force or self._meta.allow_school_change:
			try:
				self.do_move(udm_obj, lo)
			finally:
				self.invalidate_cache()
			self.set_dn(self.dn)
		else:
			logger.warning('Would like to move %s to %r. But it is not allowed!', udm_obj.dn, self)
			return False
		return True

	def do_move(self, udm_obj, lo):
		old_school, new_school = self.get_school_from_dn(self.old_dn), self.get_school_from_dn(self.dn)
		udm_obj.move(self.dn, ignore_license=1)
		if self.supports_school() and old_school and old_school != new_school:
			self.do_school_change(udm_obj, lo, old_school)

	def change_school(self, school, lo):
		if self.school in self.schools:
			self.schools.remove(self.school)
		if school not in self.schools:
			self.schools.append(school)
		self.school = school
		self.position = self.get_own_container()
		return self.move(lo, force=True)

	def do_school_change(self, udm_obj, lo, old_school):
		logger.info('Going to move %r from school %r to %r', self.old_dn, old_school, self.school)

	def remove(self, lo):
		'''
		Removes an existing UDM instance.
		Calls pre-hooks.
		If the object does not exist, returns False.
		If the object exists, removes it, returns True and
		calls post-hooks.
		'''
		self.call_hooks('pre', 'remove')
		success = self.remove_without_hooks(lo)
		if success:
			self.call_hooks('post', 'remove')
		return success

	def remove_without_hooks(self, lo):
		logger.info('Deleting %r', self)
		udm_obj = self.get_udm_object(lo)
		if udm_obj:
			try:
				udm_obj.remove(remove_childs=True)
				udm_objects.performCleanup(udm_obj)
				self.set_dn(None)
				logger.info('%r successfully removed', self)
				return True
			finally:
				self.invalidate_cache()
		logger.info('%r does not exist!', self)
		return False

	@classmethod
	def get_name_from_dn(cls, dn):
		if dn:
			try:
				name = explode_dn(dn, 1)[0]
			except ldap.DECODING_ERROR:
				name = ''
			return cls._meta.ldap_unmap_function([name])

	@classmethod
	def get_school_from_dn(cls, dn):
		return SchoolSearchBase.getOU(dn)

	@classmethod
	def find_field_label_from_name(cls, field):
		for name, attr in cls._attributes.items():
			if name == field:
				return attr.label

	def get_error_msg(self):
		error_msg = ''
		for key, errors in self.errors.iteritems():
			label = self.find_field_label_from_name(key)
			error_str = ''
			for error in errors:
				error_str += error
				if not (error.endswith('!') or error.endswith('.')):
					error_str += '.'
				error_str += ' '
			error_msg += '%s: %s' % (label, error_str)
		return error_msg[:-1]

	def get_udm_object(self, lo):
		'''Returns the UDM object that corresponds to self.
		If self._meta.name_is_unique it searches for any UDM object
		with self.name.
		If not (which is the default) it searches for self.old_dn or self.dn
		Returns None if no object was found. Caches the result, even None
		If you want to re-search, you need to explicitely set
		self._udm_obj_searched = False
		'''
		self.init_udm_module(lo)
		if self._udm_obj_searched is False or (self._udm_obj and self._udm_obj.lo.binddn != lo.binddn):
			dn = self.old_dn or self.dn
			superordinate = self.get_superordinate(lo)
			if dn is None:
				logger.debug('Getting %s UDM object: No DN!', self.__class__.__name__)
				return
			if self._meta.name_is_unique:
				if self.name is None:
					return None
				udm_name = self._attributes['name'].udm_name
				name = self.get_name_from_dn(dn)
				filter_str = '%s=%s' % (udm_name, escape_filter_chars(name))
				self._udm_obj = self.get_first_udm_obj(lo, filter_str, superordinate)
			else:
				logger.debug('Getting %s UDM object by dn: %s', self.__class__.__name__, dn)
				try:
					self._udm_obj = udm_modules.lookup(self._meta.udm_module, None, lo, scope='base', base=dn, superordinate=superordinate)[0]
				except (noObject, IndexError):
					self._udm_obj = None
				else:
					self._udm_obj.open()
			self._udm_obj_searched = True
		return self._udm_obj

	def get_school_obj(self, lo):
		from ucsschool.lib.models.school import School
		if not self.supports_school():
			return None
		school = School.cache(self.school)
		try:
			return School.from_dn(school.dn, None, lo)
		except noObject:
			logger.warning('%r does not exist!', school)
			return None

	def get_superordinate(self, lo):
		return None

	def get_own_container(self):
		if self.supports_school() and not self.school:
			return None
		return self.get_container(self.school)

	@classmethod
	def get_container(cls, school):
		'''raises NotImplementedError by default. Needs to be overridden!
		'''
		raise NotImplementedError('%s.get_container()' % (cls.__name__,))

	@classmethod
	def get_search_base(cls, school_name):
		from ucsschool.lib.models.school import School
		if school_name not in cls._search_base_cache:
			school = School(name=school_name)
			cls._search_base_cache[school_name] = SchoolSearchBase([school.name], dn=school.dn)
		return cls._search_base_cache[school_name]

	@classmethod
	def init_udm_module(cls, lo):
		if cls._meta.udm_module in cls._initialized_udm_modules:
			return
		pos = udm_uldap.position(lo.base)
		udm_modules.init(lo, pos, udm_modules.get(cls._meta.udm_module))
		cls._initialized_udm_modules.append(cls._meta.udm_module)

	@classmethod
	def get_all(cls, lo, school, filter_str=None, easy_filter=False, superordinate=None):
		'''
		Returns a list of all objects that can be found in cls.get_container() with the
		correct udm_module
		If filter_str is given, all udm properties with include_in_default_search are
		queried for that string (so that it should be the value)
		'''
		cls.init_udm_module(lo)
		complete_filter = cls._meta.udm_filter
		if easy_filter:
			filter_from_filter_str = cls.build_easy_filter(filter_str)
		else:
			filter_from_filter_str = filter_str
		if filter_from_filter_str:
			if complete_filter:
				complete_filter = conjunction('&', [complete_filter, filter_from_filter_str])
			else:
				complete_filter = filter_from_filter_str
		complete_filter = str(complete_filter)
		logger.debug('Getting all %s of %s with filter %r', cls.__name__, school, complete_filter)
		ret = []
		for udm_obj in cls.lookup(lo, school, complete_filter, superordinate=superordinate):
			udm_obj.open()
			try:
				ret.append(cls.from_udm_obj(udm_obj, school, lo))
			except UnknownModel:
				continue
		return ret

	@classmethod
	def lookup(cls, lo, school, filter_s='', superordinate=None):
		try:
			return udm_modules.lookup(cls._meta.udm_module, None, lo, filter=filter_s, base=cls.get_container(school), scope='sub', superordinate=superordinate)
		except noObject:
			logger.warning('Error while getting all %s of %s: probably %r does not exist!', cls.__name__, school, cls.get_container(school))
			return []

	@classmethod
	def _attrs_for_easy_filter(cls):
		ret = []
		module = udm_modules.get(cls._meta.udm_module)
		for key, prop in module.property_descriptions.iteritems():
			if prop.include_in_default_search:
				ret.append(key)
		return ret

	@classmethod
	def build_easy_filter(cls, filter_str):
		if filter_str:
			sanitizer = LDAPSearchSanitizer()
			filter_str = sanitizer.sanitize('filter_str', {'filter_str': filter_str})
			expressions = []
			for key in cls._attrs_for_easy_filter():
				expressions.append(expression(key, filter_str))
			if expressions:
				return conjunction('|', expressions)

	@classmethod
	def from_udm_obj(cls, udm_obj, school, lo):  # Design fault. school is part of the DN or the ucsschoolSchool attribute.
		'''Creates a new instance with attributes of the udm_obj.
		Uses get_class_for_udm_obj()
		'''
		cls.init_udm_module(lo)
		klass = cls.get_class_for_udm_obj(udm_obj, school)
		if klass is None:
			logger.warning('UDM object %s does not correspond to a class in UCS school lib!', udm_obj.dn)
			raise UnknownModel(udm_obj.dn, cls)
		if klass is not cls:
			logger.info('UDM object %s is not %s, but actually %s', udm_obj.dn, cls.__name__, klass.__name__)
			if not issubclass(klass, cls):
				# security!
				# ExamStudent must not be converted into Teacher/Student/etc.,
				# SchoolClass must not be converted into ComputerRoom
				# while Group must be converted into ComputerRoom, etc. and User must be converted into Student, etc.
				raise WrongModel(udm_obj.dn, klass, cls)
			return klass.from_udm_obj(udm_obj, school, lo)
		udm_obj.open()
		attrs = {'school': cls.get_school_from_dn(udm_obj.dn) or school}  # TODO: is this adjustment okay?
		for name, attr in cls._attributes.iteritems():
			if attr.udm_name:
				udm_value = udm_obj[attr.udm_name]
				if udm_value == '':
					udm_value = None
				attrs[name] = udm_value
		obj = cls(**deepcopy(attrs))
		obj.set_dn(udm_obj.dn)
		obj._udm_obj_searched = True
		obj._udm_obj = udm_obj
		return obj

	@classmethod
	def get_class_for_udm_obj(cls, udm_obj, school):
		'''Returns cls by default.
		Can be overridden for base classes:
		class User(UCSSchoolHelperAbstractClass):
			@classmethod
			def get_class_for_udm_obj(cls, udm_obj, school)
				if something:
					return SpecialUser
				return cls

		class SpecialUser(User):
			pass

		Now, User.get_all() will return a list of User and SpecialUser objects
		If this function returns None for a udm_obj, that obj will not
		yield a new instance in get_all() and from_udm_obj() will return None
		for that udm_obj
		'''
		return cls

	def __repr__(self):
		dn = self.dn
		dn = '%r, old_dn=%r' % (dn, self.old_dn) if dn != self.old_dn else repr(dn)
		if self.supports_school():
			return '%s(name=%r, school=%r, dn=%s)' % (self.__class__.__name__, self.name, self.school, dn)
		else:
			return '%s(name=%r, dn=%s)' % (self.__class__.__name__, self.name, dn)

	def __lt__(self, other):
		return self.name < other.name

	@classmethod
	def from_dn(cls, dn, school, lo, superordinate=None):
		'''Returns a new instance based on the UDM object found at dn
		raises noObject if the udm_module does not match the dn
		or dn is not found
		'''
		cls.init_udm_module(lo)
		if school is None and cls.supports_school():
			school = cls.get_school_from_dn(dn)
			if school is None:
				logger.warn('Unable to guess school from %r', dn)
		try:
			logger.debug('Looking up %s with dn %r', cls.__name__, dn)
			udm_obj = udm_modules.lookup(cls._meta.udm_module, None, lo, filter=cls._meta.udm_filter, base=dn, scope='base', superordinate=superordinate)[0]
		except IndexError:
			# happens when cls._meta.udm_module does not "match" the dn
			raise WrongObjectType(dn, cls)
		return cls.from_udm_obj(udm_obj, school, lo)

	@classmethod
	def get_only_udm_obj(cls, lo, filter_str, superordinate=None, base=None):
		'''Returns the one UDM object of class cls._meta.udm_module that
		matches a given filter.
		If more than one is found, a MultipleObjectsError is raised
		If none is found, None is returned
		'''
		cls.init_udm_module(lo)
		if cls._meta.udm_filter:
			filter_str = '(&(%s)(%s))' % (cls._meta.udm_filter, filter_str)
		logger.debug('Getting %s UDM object by filter: %s', cls.__name__, filter_str)
		objs = udm_modules.lookup(cls._meta.udm_module, None, lo, scope='sub', base=base or ucr.get('ldap/base'), filter=str(filter_str), superordinate=superordinate)
		if len(objs) == 0:
			return None
		if len(objs) > 1:
			raise MultipleObjectsError(objs)
		obj = objs[0]
		obj.open()
		return obj

	@classmethod
	def get_first_udm_obj(cls, lo, filter_str, superordinate=None):
		'''Returns the first UDM object of class cls._meta.udm_module that
		matches a given filter
		'''
		try:
			return cls.get_only_udm_obj(lo, filter_str, superordinate)
		except MultipleObjectsError as exc:
			obj = exc.objs[0]
			obj.open()
			return obj

	@classmethod
	def find_udm_superordinate(cls, dn, lo):
		module = udm_modules.get(cls._meta.udm_module)
		return udm_objects.get_superordinate(module, None, lo, dn)

	def to_dict(self):
		'''Returns a dictionary somewhat representing this instance.
		This dictionary is usually used when sending the instance to
		a browser as JSON.
		By default the attributes are present as well as the dn and
		the udm_module.'''
		ret = {'$dn$': self.dn, 'objectType': self._meta.udm_module}
		for name, attr in self._attributes.iteritems():
			if not attr.internal:
				ret[name] = getattr(self, name)
		return ret

	def _map_func_name_to_code(self, func_name):
		if func_name == 'create':
			return 'A'
		elif func_name == 'modify':
			return 'M'
		elif func_name == 'remove':
			return 'D'
		elif func_name == 'move':
			return 'MV'

	def _build_hook_line(self, *args):
		attrs = []
		for arg in args:
			val = arg
			if arg is None:
				val = ''
			if arg is False:
				val = 0
			if arg is True:
				val = 1
			attrs.append(str(val))
		return self.hook_sep_char.join(attrs)
