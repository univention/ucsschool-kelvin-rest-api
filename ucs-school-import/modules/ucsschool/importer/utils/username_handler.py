import re

from ldap.filter import escape_filter_chars, filter_format
from univention.admin.uexceptions import noObject
from ucsschool.importer.utils.ldap_connection import get_admin_connection
from ucsschool.importer.exceptions import FormatError
from ucsschool.importer.utils.logging2udebug import get_logger


class UsernameHandler(object):
	username_pattern = re.compile(r"\[.*?\]")

	def __init__(self, username_max_length):
		self.username_max_length = username_max_length
		self.logger = get_logger()
		self.connection, self.position = get_admin_connection()

	def add_to_ldap(self, username, first_number):
		assert isinstance(username, basestring)
		assert isinstance(first_number, basestring)
		self.connection.add(
			filter_format("cn=%s,cn=unique-usernames,cn=ucsschool,cn=univention,%s", (username,
				self.connection.base)),
			[
				("objectClass", "ucsschoolUsername"),
				("ucsschoolUsernameNextNumber", escape_filter_chars(first_number))
			]
		)

	def get_next_number(self, username):
		assert isinstance(username, basestring)
		try:
			return self.connection.get(
				filter_format("cn=%s,cn=unique-usernames,cn=ucsschool,cn=univention,%s", (username,
					self.connection.base)),
				attr=["ucsschoolUsernameNextNumber"])["ucsschoolUsernameNextNumber"][0]
		except KeyError:
			raise noObject("Username '{}' not found.".format(username))

	def get_and_raise_number(self, username):
		assert isinstance(username, basestring)
		cur = self.get_next_number(username)
		next = int(cur) + 1
		self.connection.modify(
			filter_format("cn=%s,cn=unique-usernames,cn=ucsschool,cn=univention,%s", (username,
				self.connection.base)),
			[("ucsschoolUsernameNextNumber", cur, str(next))]
		)
		return cur

	def format_username(self, name):
		"""
		Create a username from name, possibly replacing a counter variable.
		* This is intended to be called before/by/after ImportUser.format_from_scheme().
		* Supports inserting the counter anywhere in the name, as long as its
		length does not overflow username_max_length.
		* Only one counter variable is allowed.
		* Counters should run only to 999. The algorithm will not honor
		username_max_length for higher numbers!
		* Subclass->override username_patterns() and the called methods to support
		other schemes than [ALWAYSCOUNTER] and [COUNTER2] or change their meaning.

		:param name: str: username, possibly a template
		:return: str: unique username
		"""
		assert isinstance(name, basestring)
		res = name
		cut_pos = self.username_max_length - 3  # numbers >999 are not supported
		match = self.username_pattern.search(name)

		if match:
			variable = match.group()
			start = match.start()
			end = match.end()
		else:
			if len(name) > cut_pos:
				res = name[:cut_pos]
				self.logger.warn("Username %r to long, shortened to %r.", name, res)
			return res

		if len(self.username_pattern.split(name)) > 2:
			raise FormatError("More than one counter variable found in username scheme '{}'.".format(name), name, name)

		if start == 0 and end == len(name):
			raise FormatError("No username in '{}'.".format(name), name, name)

		try:
			func = self.username_patterns[variable]
		except KeyError as exc:
			raise FormatError("Unknown variable name '{}' in username scheme '{}': {}".format(variable, name, exc),
				variable, name)
		except AttributeError as exc:
			raise FormatError("No method '{}' can be found for variable name '{}' in username scheme '{}': {}".format(
				self.username_patterns[variable], variable, name, exc), variable, name)

		base_name = "".join(self.username_pattern.split(name))
		if len(base_name) > cut_pos:
			# base name without variable to long, we have to shorten it
			# numbers will only be appended, no inserting possible anymore
			res = base_name[:cut_pos]
			insert_position = cut_pos
			self.logger.warn("Username %r to long, shortened to %r.", name, res)
		else:
			insert_position = start
			res = u"{}{}".format(name[:start], name[end:])

		counter = func(res)
		ret = "{}{}{}".format(res[:insert_position], counter, res[insert_position:])
		return ret

	@property
	def username_patterns(self):
		"""
		Subclass->override this to support other variables than [ALWAYSCOUNTER]
		and [COUNTER2] or change their meaning. Add/Modify corresponding
		methods in your subclass.
		Variables have to start with '[' and end with ']'.
		Methods will be found with getattr(self, "method name").

		:return: dict: variable name -> function
		"""
		return {
			"[ALWAYSCOUNTER]": self.always_counter,
			"[COUNTER2]": self.counter2
		}

	def always_counter(self, name_base):
		"""
		[ALWAYSCOUNTER]

		:param name_base: str: the (base) username
		:return: str: number to append to username
		"""
		return self._counters(name_base, "1")

	def counter2(self, name_base):
		"""
		[COUNTER2]

		:param name_base: str: the (base) username
		:return: str: number to append to username
		"""
		return self._counters(name_base, "")

	def _counters(self, name_base, first_time):
		"""
		Common code of always_counter() and counter2().
		"""
		try:
			num = self.get_and_raise_number(name_base)
		except noObject:
			num = first_time
			self.add_to_ldap(name_base, "2")
		return num