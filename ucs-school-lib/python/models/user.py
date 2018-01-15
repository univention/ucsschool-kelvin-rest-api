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

from ldap.dn import escape_dn_chars, explode_dn
from ldap.filter import escape_filter_chars, filter_format

from ucsschool.lib.roles import role_pupil, role_teacher, role_staff
from ucsschool.lib.models.utils import create_passwd
from ucsschool.lib.models.attributes import Username, Firstname, Lastname, Birthday, Email, Password, Disabled, SchoolClassesAttribute, Schools
from ucsschool.lib.models.base import UCSSchoolHelperAbstractClass, UnknownModel, WrongModel
from ucsschool.lib.models.school import School
from ucsschool.lib.models.group import Group, SchoolClass, WorkGroup, SchoolGroup
from ucsschool.lib.models.computer import AnyComputer
from ucsschool.lib.models.misc import MailDomain
from ucsschool.lib.models.utils import ucr, _, logger

from univention.admin.uexceptions import noObject
from univention.admin.filter import conjunction, parse
import univention.admin.modules as udm_modules


class User(UCSSchoolHelperAbstractClass):
	name = Username(_('Username'), aka=['Username', 'Benutzername'])
	schools = Schools(_('Schools'))
	firstname = Firstname(_('First name'), aka=['First name', 'Vorname'], required=True, unlikely_to_change=True)
	lastname = Lastname(_('Last name'), aka=['Last name', 'Nachname'], required=True, unlikely_to_change=True)
	birthday = Birthday(_('Birthday'), aka=['Birthday', 'Geburtstag'], unlikely_to_change=True)
	email = Email(_('Email'), aka=['Email', 'E-Mail'], unlikely_to_change=True)
	password = Password(_('Password'), aka=['Password', 'Passwort'])
	disabled = Disabled(_('Disabled'), aka=['Disabled', 'Gesperrt'])
	school_classes = SchoolClassesAttribute(_('Class'), aka=['Class', 'Klasse'])

	type_name = None
	type_filter = '(|(objectClass=ucsschoolTeacher)(objectClass=ucsschoolStaff)(objectClass=ucsschoolStudent))'

	_profile_path_cache = {}
	_samba_home_path_cache = {}
	# _samba_home_path_cache is invalidated in School.invalidate_cache()

	roles = []
	default_options = ()

	def __init__(self, *args, **kwargs):
		super(User, self).__init__(*args, **kwargs)
		if self.school_classes is None:
			self.school_classes = {}  # set a dict for Staff
		if self.school and not self.schools:
			self.schools.append(self.school)

	@classmethod
	def shall_create_mail_domain(cls):
		return ucr.is_true('ucsschool/import/generate/mail/domain')

	def get_roleshare_home_subdir(self):
		from ucsschool.lib.roleshares import roleshare_home_subdir
		return roleshare_home_subdir(self.school, self.roles, ucr)

	def get_samba_home_drive(self):
		return ucr.get('ucsschool/import/set/homedrive')

	def get_samba_netlogon_script_path(self):
		return ucr.get('ucsschool/import/set/netlogon/script/path')

	def get_samba_home_path(self, lo):
		school = School.cache(self.school)
		# if defined then use UCR value
		ucr_variable = ucr.get('ucsschool/import/set/sambahome')
		if ucr_variable is not None:
			samba_home_path = r'\\%s' % ucr_variable.strip('\\')
		# in single server environments the master is always the fileserver
		elif ucr.is_true('ucsschool/singlemaster', False):
			samba_home_path = r'\\%s' % ucr.get('hostname')
		# if there's a cached result then use it
		elif school.dn not in self._samba_home_path_cache:
			samba_home_path = None
			# get windows home server from OU object
			school = self.get_school_obj(lo)
			home_share_file_server = school.home_share_file_server
			if home_share_file_server:
				samba_home_path = r'\\%s' % self.get_name_from_dn(home_share_file_server)
			self._samba_home_path_cache[school.dn] = samba_home_path
		else:
			samba_home_path = self._samba_home_path_cache[school.dn]
		if samba_home_path is not None:
			return r'%s\%s' % (samba_home_path, self.name)

	def get_profile_path(self, lo):
		ucr_variable = ucr.get('ucsschool/import/set/serverprofile/path')
		if ucr_variable is not None:
			return ucr_variable
		school = School.cache(self.school)
		if school.dn not in self._profile_path_cache:
			profile_path = r'%s\%%USERNAME%%\windows-profiles\default'
			for computer in AnyComputer.get_all(lo, self.school, 'univentionService=Windows Profile Server'):
				profile_path = profile_path % (r'\\%s' % computer.name)
				break
			else:
				profile_path = profile_path % '%LOGONSERVER%'
			self._profile_path_cache[school.dn] = profile_path
		return self._profile_path_cache[school.dn]

	def is_student(self, lo):
		return self.__check_object_class(lo, 'ucsschoolStudent', self._legacy_is_student)

	def is_exam_student(self, lo):
		return self.__check_object_class(lo, 'ucsschoolExam', self._legacy_is_exam_student)

	def is_teacher(self, lo):
		return self.__check_object_class(lo, 'ucsschoolTeacher', self._legacy_is_teacher)

	def is_staff(self, lo):
		return self.__check_object_class(lo, 'ucsschoolStaff', self._legacy_is_staff)

	def is_administrator(self, lo):
		return self.__check_object_class(lo, 'ucsschoolAdministrator', self._legacy_is_admininstrator)

	@classmethod
	def _legacy_is_student(cls, school, dn):
		logger.warning('Using deprecated method is_student()')
		return dn.endswith(cls.get_search_base(school).students)

	@classmethod
	def _legacy_is_exam_student(cls, school, dn):
		logger.warning('Using deprecated method is_exam_student()')
		return dn.endswith(cls.get_search_base(school).examUsers)

	@classmethod
	def _legacy_is_teacher(cls, school, dn):
		logger.warning('Using deprecated method is_teacher()')
		search_base = cls.get_search_base(school)
		return dn.endswith(search_base.teachers) or dn.endswith(search_base.teachersAndStaff) or dn.endswith(search_base.admins)

	@classmethod
	def _legacy_is_staff(cls, school, dn):
		logger.warning('Using deprecated method is_staff()')
		search_base = cls.get_search_base(school)
		return dn.endswith(search_base.staff) or dn.endswith(search_base.teachersAndStaff)

	@classmethod
	def _legacy_is_admininstrator(cls, school, dn):
		logger.warning('Using deprecated method is_admininstrator()')
		return dn.endswith(cls.get_search_base(school).admins)

	def __check_object_class(self, lo, object_class, fallback):
		obj = self.get_udm_object(lo)
		if not obj:
			raise noObject('Could not read %r' % (self.dn,))
		if 'ucsschoolSchool' in obj.oldattr:
			return object_class in obj.oldattr.get('objectClass', [])
		return fallback(self.school, self.dn)

	@classmethod
	def get_class_for_udm_obj(cls, udm_obj, school):
		ocs = set(udm_obj.oldattr.get('objectClass', []))
		if ocs >= set(['ucsschoolTeacher', 'ucsschoolStaff']):
			return TeachersAndStaff
		if ocs >= set(['ucsschoolExam', 'ucsschoolStudent']):
			return ExamStudent
		if 'ucsschoolTeacher' in ocs:
			return Teacher
		if 'ucsschoolStaff' in ocs:
			return Staff
		if 'ucsschoolStudent' in ocs:
			return Student
		if 'ucsschoolAdministrator' in ocs:
			return Teacher  # we have no class for a school administrator

		# legacy DN based checks
		if cls._legacy_is_student(school, udm_obj.dn):
			return Student
		if cls._legacy_is_teacher(school, udm_obj.dn):
			if cls._legacy_is_staff(school, udm_obj.dn):
				return TeachersAndStaff
			return Teacher
		if cls._legacy_is_staff(school, udm_obj.dn):
			return Staff
		if cls._legacy_is_exam_student(school, udm_obj.dn):
			return ExamStudent

		return User

	@classmethod
	def from_udm_obj(cls, udm_obj, school, lo):
		obj = super(User, cls).from_udm_obj(udm_obj, school, lo)
		obj.password = None
		obj.school_classes = cls.get_school_classes(udm_obj, obj)
		return obj

	def do_create(self, udm_obj, lo):
		if not self.schools:
			self.schools = [self.school]
		self.set_default_options(udm_obj)
		self.create_mail_domain(lo)
		password_created = False
		if not self.password:
			logger.debug('No password given. Generating random one')
			old_password = self.password  # None or ''
			self.password = create_passwd(dn=self.dn)
			password_created = True
		udm_obj['primaryGroup'] = self.primary_group_dn(lo)
		udm_obj['groups'] = self.groups_used(lo)
		subdir = self.get_roleshare_home_subdir()
		udm_obj['unixhome'] = '/home/' + os.path.join(subdir, self.name)
		udm_obj['overridePWHistory'] = '1'
		udm_obj['overridePWLength'] = '1'
		if self.disabled is None:
			udm_obj['disabled'] = 'none'
		if 'mailbox' in udm_obj:
			udm_obj['mailbox'] = '/var/spool/%s/' % self.name
		samba_home = self.get_samba_home_path(lo)
		if samba_home:
			udm_obj['sambahome'] = samba_home
		profile_path = self.get_profile_path(lo)
		if profile_path:
			udm_obj['profilepath'] = profile_path
		home_drive = self.get_samba_home_drive()
		if home_drive is not None:
			udm_obj['homedrive'] = home_drive
		script_path = self.get_samba_netlogon_script_path()
		if script_path is not None:
			udm_obj['scriptpath'] = script_path
		success = super(User, self).do_create(udm_obj, lo)
		if password_created:
			# to not show up in host_hooks
			self.password = old_password
		return success

	def do_modify(self, udm_obj, lo):
		self.create_mail_domain(lo)
		self.password = self.password or None

		removed_schools = set(udm_obj['school']) - set(self.schools)
		if removed_schools:
			# change self.schools back, so schools can be removed by remove_from_school()
			self.schools = udm_obj['school']
		for removed_school in removed_schools:
			logger.info('Removing %r from school %r...', self, removed_school)
			if not self.remove_from_school(removed_school, lo):
				logger.error('Error removing %r from school %r.', self, removed_school)
				return False

		mandatory_groups = self.groups_used(lo)
		for group_dn in udm_obj['groups'][:]:
			logger.debug('Checking group %s for removal', group_dn)
			if group_dn not in mandatory_groups:
				logger.debug('Group not mandatory! Part of a school?')
				try:
					school_class = SchoolClass.from_dn(group_dn, None, lo)
				except noObject:
					logger.debug('No. Leaving it alone...')
					continue
				logger.debug('Yes, part of %s!', school_class.school)
				if school_class.school not in self.school_classes:
					continue  # if the key isn't set we don't change anything to the groups. to remove the groups it has to be an empty list
				classes = self.school_classes[school_class.school]
				remove = school_class.name not in classes and school_class.get_relative_name() not in classes
				if remove:
					logger.debug('Removing it!')
					udm_obj['groups'].remove(group_dn)
				else:
					logger.debug('Leaving it alone: Part of own school and either non-school class or new school classes were not defined at all')
		for group_dn in mandatory_groups:
			logger.debug('Checking group %s for adding', group_dn)
			if group_dn not in udm_obj['groups']:
				logger.debug('Group is not yet part of the user. Adding...')
				udm_obj['groups'].append(group_dn)
		return super(User, self).do_modify(udm_obj, lo)

	def do_school_change(self, udm_obj, lo, old_school):
		super(User, self).do_school_change(udm_obj, lo, old_school)
		school = self.school

		logger.info('User is part of the following groups: %r', udm_obj['groups'])
		self.remove_from_groups_of_school(old_school, lo)
		self._udm_obj_searched = False
		self.school_classes.pop(old_school, None)
		udm_obj = self.get_udm_object(lo)
		udm_obj['primaryGroup'] = self.primary_group_dn(lo)
		groups = set(udm_obj['groups'])
		at_least_groups = set(self.groups_used(lo))
		if (groups | at_least_groups) != groups:
			udm_obj['groups'] = list(groups | at_least_groups)
		subdir = self.get_roleshare_home_subdir()
		udm_obj['unixhome'] = '/home/' + os.path.join(subdir, self.name)
		samba_home = self.get_samba_home_path(lo)
		if samba_home:
			udm_obj['sambahome'] = samba_home
		profile_path = self.get_profile_path(lo)
		if profile_path:
			udm_obj['profilepath'] = profile_path
		home_drive = self.get_samba_home_drive()
		if home_drive is not None:
			udm_obj['homedrive'] = home_drive
		script_path = self.get_samba_netlogon_script_path()
		if script_path is not None:
			udm_obj['scriptpath'] = script_path
		if udm_obj['departmentNumber'] == old_school:
			udm_obj['departmentNumber'] = school
		if school not in udm_obj['school']:
			udm_obj['school'].append(school)
		if old_school in udm_obj['school']:
			udm_obj['school'].remove(old_school)
		udm_obj.modify(ignore_license=True)

	def _alter_udm_obj(self, udm_obj):
		if self.email is not None:
			udm_obj['e-mail'] = self.email
		udm_obj['departmentNumber'] = self.school
		ret = super(User, self)._alter_udm_obj(udm_obj)
		return ret

	def get_mail_domain(self):
		if self.email:
			domain_name = self.email.split('@')[-1]
			return MailDomain.cache(domain_name)

	def create_mail_domain(self, lo):
		mail_domain = self.get_mail_domain()
		if mail_domain is not None and not mail_domain.exists(lo):
			if self.shall_create_mail_domain():
				mail_domain.create(lo)
			else:
				logger.warning('Not allowed to create %r.', mail_domain)

	def set_default_options(self, udm_obj):
		for option in self.get_default_options():
			if option not in udm_obj.options:
				udm_obj.options.append(option)

	@classmethod
	def get_default_options(cls):
		options = set()
		for kls in cls.__bases__:  # u-s-import uses multiple inheritance, we have to cover all parents
			try:
				options.update(kls.get_default_options())
			except AttributeError:
				pass
		options.update(cls.default_options)
		return options

	def get_specific_groups(self, lo):
		groups = self.get_domain_users_groups()
		for school_class in self.get_school_class_objs():
			groups.append(self.get_class_dn(school_class.name, school_class.school, lo))
		return groups

	def validate(self, lo, validate_unlikely_changes=False):
		super(User, self).validate(lo, validate_unlikely_changes)
		try:
			udm_obj = self.get_udm_object(lo)
		except UnknownModel:
			udm_obj = None
		except WrongModel as exc:
			udm_obj = None
			self.add_error('name', _('It is not supported to change the role of a user. %(old_role)s %(name)s cannot become a %(new_role)s.') % {
				'old_role': exc.model.type_name,
				'name': self.name,
				'new_role': self.type_name
			})
		if udm_obj:
			original_class = self.get_class_for_udm_obj(udm_obj, self.school)
			if original_class is not self.__class__:
				self.add_error('name', _('It is not supported to change the role of a user. %(old_role)s %(name)s cannot become a %(new_role)s.') % {
					'old_role': original_class.type_name,
					'name': self.name,
					'new_role': self.type_name
				})
		if self.email:
			name, email = escape_filter_chars(self.name), escape_filter_chars(self.email)
			if self.get_first_udm_obj(lo, '&(!(uid=%s))(mailPrimaryAddress=%s)' % (name, email)):
				self.add_error('email', _('The email address is already taken by another user. Please change the email address.'))
			# mail_domain = self.get_mail_domain(lo)
			# if not mail_domain.exists(lo) and not self.shall_create_mail_domain():
			# 	self.add_error('email', _('The mail domain is unknown. Please change the email address or create the mail domain "%s" using the Univention Directory Manager.') % mail_domain.name)

	def remove_from_school(self, school, lo):
		if not self.exists(lo):
			logger.warning('User does not exists, not going to remove.')
			return False
		try:
			(self.schools or [school]).remove(school)
		except ValueError:
			logger.warning('User is not part of school %r. Not removing.', school)
			return False
		if not self.schools:
			logger.warning('User %r not part of any school, removing it.', self)
			return self.remove(lo)
		if self.school == school:
			if not self.change_school(self.schools[0], lo):
				return False
		else:
			self.remove_from_groups_of_school(school, lo)
		self.school_classes.pop(school, None)
		return True

	def remove_from_groups_of_school(self, school, lo):
		for cls in (SchoolClass, WorkGroup, SchoolGroup):
			for group in cls.get_all(lo, school, filter_format('uniqueMember=%s', (self.dn,))):
				try:
					group.users.remove(self.dn)
				except ValueError:
					pass
				else:
					logger.info('Removing %r from group %r of school %r.', self.dn, group.dn, school)
					group.modify(lo)

	def get_group_dn(self, group_name, school):
		return Group.cache(group_name, school).dn

	def get_class_dn(self, class_name, school, lo):
		# Bug #32337: check if the class exists without OU prefix
		# if it does not exist the class name with OU prefix is used
		school_class = SchoolClass.cache(class_name, school)
		if school_class.get_relative_name() == school_class.name:
			if not school_class.exists(lo):
				class_name = '%s-%s' % (school, class_name)
				school_class = SchoolClass.cache(class_name, school)
		return school_class.dn

	def primary_group_dn(self, lo):
		dn = self.get_group_dn('Domain Users %s' % self.school, self.school)
		return self.get_or_create_group_udm_object(dn, lo).dn

	def get_domain_users_groups(self):
		return [self.get_group_dn('Domain Users %s' % school, school) for school in self.schools]

	def get_students_groups(self):
		prefix = ucr.get('ucsschool/ldap/default/groupprefix/pupils', 'schueler-')
		return [self.get_group_dn('%s%s' % (prefix, school), school) for school in self.schools]

	def get_teachers_groups(self):
		prefix = ucr.get('ucsschool/ldap/default/groupprefix/teachers', 'lehrer-')
		return [self.get_group_dn('%s%s' % (prefix, school), school) for school in self.schools]

	def get_staff_groups(self):
		prefix = ucr.get('ucsschool/ldap/default/groupprefix/staff', 'mitarbeiter-')
		return [self.get_group_dn('%s%s' % (prefix, school), school) for school in self.schools]

	def groups_used(self, lo):
		group_dns = self.get_specific_groups(lo)

		for group_dn in group_dns:
			self.get_or_create_group_udm_object(group_dn, lo)

		return group_dns

	@classmethod
	def get_or_create_group_udm_object(cls, group_dn, lo, fresh=False):
		name = cls.get_name_from_dn(group_dn)
		school = cls.get_school_from_dn(group_dn)
		if Group.is_school_class(school, group_dn):
			group = SchoolClass.cache(name, school)
		else:
			group = Group.cache(name, school)
		if fresh:
			group._udm_obj_searched = False
		group.create(lo)
		return group

	def is_active(self):
		return self.disabled != 'all'

	def build_hook_line(self, hook_time, func_name):
		code = self._map_func_name_to_code(func_name)
		is_teacher = isinstance(self, Teacher) or isinstance(self, TeachersAndStaff)
		is_staff = isinstance(self, Staff) or isinstance(self, TeachersAndStaff)
		school_class = ','.join(self.school_classes.get(self.school, []))  # legacy format: only classes of the primary school
		return self._build_hook_line(
			code,
			self.name,
			self.lastname,
			self.firstname,
			self.school,
			school_class,
			'',  # TODO: rights?
			self.email,
			is_teacher,
			self.is_active(),
			is_staff,
			self.password,
		)

	def to_dict(self):
		ret = super(User, self).to_dict()
		display_name = []
		if self.firstname:
			display_name.append(self.firstname)
		if self.lastname:
			display_name.append(self.lastname)
		ret['display_name'] = ' '.join(display_name)
		school_classes = {}
		for school_class in self.get_school_class_objs():
			school_classes.setdefault(school_class.school, []).append(school_class.name)
		ret['school_classes'] = school_classes
		ret['type_name'] = self.type_name
		ret['type'] = self.__class__.__name__
		ret['type'] = ret['type'][0].lower() + ret['type'][1:]
		return ret

	def get_school_class_objs(self):
		ret = []
		for school, classes in self.school_classes.iteritems():
			for school_class in classes:
				ret.append(SchoolClass.cache(school_class, school))
		return ret

	@classmethod
	def get_school_classes(cls, udm_obj, obj):
		school_classes = {}
		for group in udm_obj['groups']:
			for school in obj.schools:
				if Group.is_school_class(school, group):
					school_class_name = cls.get_name_from_dn(group)
					school_classes.setdefault(school, []).append(school_class_name)
		return school_classes

	@classmethod
	def get_container(cls, school):
		return cls.get_search_base(school).users

	@classmethod
	def lookup(cls, lo, school, filter_s='', superordinate=None):
		filter_object_type = conjunction('&', [parse(cls.type_filter), parse(filter_format('ucsschoolSchool=%s', [school]))])
		if filter_s:
			filter_object_type = conjunction('&', [filter_object_type, parse(filter_s)])
		objects = udm_modules.lookup(cls._meta.udm_module, None, lo, filter=unicode(filter_object_type), scope='sub', superordinate=superordinate)
		objects.extend(obj for obj in super(User, cls).lookup(lo, school, filter_s, superordinate=superordinate) if not any(obj.dn == x.dn for x in objects))
		return objects

	class Meta:
		udm_module = 'users/user'
		name_is_unique = True
		allow_school_change = False


class Student(User):
	type_name = _('Student')
	type_filter = '(&(objectClass=ucsschoolStudent)(!(objectClass=ucsschoolExam)))'
	roles = [role_pupil]
	default_options = ('ucsschoolStudent',)

	def do_school_change(self, udm_obj, lo, old_school):
		try:
			exam_user = ExamStudent.from_student_dn(lo, old_school, self.old_dn)
		except noObject as exc:
			logger.info('No exam user for %r found: %s', self.old_dn, exc)
		else:
			logger.info('Removing exam user %r', exam_user.dn)
			exam_user.remove(lo)

		super(Student, self).do_school_change(udm_obj, lo, old_school)

	@classmethod
	def get_container(cls, school):
		return cls.get_search_base(school).students

	@classmethod
	def get_exam_container(cls, school):
		return cls.get_search_base(school).examUsers

	def get_specific_groups(self, lo):
		groups = super(Student, self).get_specific_groups(lo)
		groups.extend(self.get_students_groups())
		return groups


class Teacher(User):
	type_name = _('Teacher')
	type_filter = '(&(objectClass=ucsschoolTeacher)(!(objectClass=ucsschoolStaff)))'
	roles = [role_teacher]
	default_options = ('ucsschoolTeacher',)

	@classmethod
	def get_container(cls, school):
		return cls.get_search_base(school).teachers

	def get_specific_groups(self, lo):
		groups = super(Teacher, self).get_specific_groups(lo)
		groups.extend(self.get_teachers_groups())
		return groups


class Staff(User):
	school_classes = None
	type_name = _('Staff')
	roles = [role_staff]
	type_filter = '(&(!(objectClass=ucsschoolTeacher))(objectClass=ucsschoolStaff))'
	default_options = ('ucsschoolStaff',)

	@classmethod
	def get_container(cls, school):
		return cls.get_search_base(school).staff

	def get_samba_home_path(self, lo):
		"""	Do not set sambaHomePath for staff users. """
		return None

	def get_samba_home_drive(self):
		"""	Do not set sambaHomeDrive for staff users. """
		return None

	def get_samba_netlogon_script_path(self):
		"""	Do not set sambaLogonScript for staff users. """
		return None

	def get_profile_path(self, lo):
		"""	Do not set sambaProfilePath for staff users. """
		return None

	def get_school_class_objs(self):
		return []

	@classmethod
	def get_school_classes(cls, udm_obj, obj):
		return {}

	def get_specific_groups(self, lo):
		groups = super(Staff, self).get_specific_groups(lo)
		groups.extend(self.get_staff_groups())
		return groups


class TeachersAndStaff(Teacher):
	type_name = _('Teacher and Staff')
	type_filter = '(&(objectClass=ucsschoolStaff)(objectClass=ucsschoolTeacher))'
	roles = [role_teacher, role_staff]
	default_options = ('ucsschoolStaff',)

	@classmethod
	def get_container(cls, school):
		return cls.get_search_base(school).teachersAndStaff

	def get_specific_groups(self, lo):
		groups = super(TeachersAndStaff, self).get_specific_groups(lo)
		groups.extend(self.get_staff_groups())
		return groups


class ExamStudent(Student):
	type_name = _('Exam student')
	type_filter = '(&(objectClass=ucsschoolStudent)(objectClass=ucsschoolExam))'
	default_options = ('ucsschoolExam',)

	@classmethod
	def get_container(cls, school):
		return cls.get_search_base(school).examUsers

	@classmethod
	def from_student_dn(cls, lo, school, dn):
		examUserPrefix = ucr.get('ucsschool/ldap/default/userprefix/exam', 'exam-')
		dn = 'uid=%s%s,%s' % (escape_dn_chars(examUserPrefix), explode_dn(dn, True)[0], cls.get_container(school))
		return cls.from_dn(dn, school, lo)
