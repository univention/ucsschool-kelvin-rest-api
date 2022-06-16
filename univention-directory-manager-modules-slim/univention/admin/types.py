# -*- coding: utf-8 -*-
#
# Copyright 2019-2022 Univention GmbH
#
# https://www.univention.de/
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
# <https://www.gnu.org/licenses/>.

"""
|UDM| type definitions.
"""

from __future__ import absolute_import

import datetime
import inspect
import logging
import time
from typing import Optional, Sequence, Type, Union  # noqa: F401

import six

from .localization import translation
from .uexceptions import valueError, valueInvalidSyntax

translation = translation("univention/admin")
_ = translation.translate

if six.PY3:
    unicode = str
    long = int

_Types = Union[Type[object], Sequence[Type[object]]]

logger = logging.getLogger(__name__)


class TypeHint(object):
    """ """

    _python_types = object  # type: _Types

    @property
    def _json_type(self):
        # in most cases, the python type is equivalent to the JSON type
        return self._python_types

    _openapi_type = None  # type: Optional[str]
    _openapi_format = None  # type: Optional[str]
    _openapi_regex = None  # type: Optional[str]
    _openapi_example = None  # type: Optional[str]
    _openapi_readonly = None  # type: Optional[bool]
    _openapi_writeonly = None  # type: Optional[bool]
    _openapi_nullable = True  # everything which can be removed is nullable

    _html_element = None
    _html_input_type = None

    _encoding = None  # type: Optional[str]
    _minimum = float("-inf")
    _maximum = float("inf")

    _required = False
    _default_value = None
    _default_search_value = None

    _only_printable = False
    _allow_empty_value = False
    _encodes_none = False
    """None is a valid value for the syntax class, otherwise None means remove"""
    _blacklist = ()
    # _error_message

    _dependencies = None

    def __init__(self, property, property_name):
        self.property = property
        self.property_name = property_name
        self.syntax = self._syntax

    @property
    def _syntax(self):
        # ensure we have an instance of the syntax class and not the type
        syntax = self.property.syntax
        return syntax() if isinstance(syntax, type) else syntax

    def decode(self, value):
        """
        Decode the given value from an UDM object's property into a python type.
        This must be graceful. Invalid values set at UDM object properties should not cause an exception!

        .. note:: Do not overwrite in subclass!

        .. seealso:: overwrite :func:`univention.admin.types.TypeHint.decode_value` instead.
        """
        if value is None:
            return
        return self.decode_value(value)

    def encode(self, value):
        """Encode a value of python type into a string / list / None / etc. suitable for setting at the UDM object.

        .. note:: Do not overwrite in subclass!

        .. seealso:: overwrite :func:`univention.admin.types.TypeHint.encode_value` instead.
        """
        if value is None and not self._encodes_none:
            return

        self.type_check(value)
        self.type_check_subitems(value)
        return self.encode_value(value)

    def decode_json(self, value):
        return self.to_json_type(self.decode(value))

    def encode_json(self, value):
        return self.encode(self.from_json_type(value))

    def to_json_type(self, value):
        """Transform the value resulting from :func:`self.decode` into something suitable to transmit via JSON.

        For example, a python datetime.date object into the JSON string with a date format "2019-08-30".
        """
        if value is None:
            return
        value = self._to_json_type(value)
        if isinstance(value, bytes):
            # fallback for wrong implemented types
            # JSON cannot handle non-UTF-8 bytes
            value = value.decode("utf-8", "strict")
        return value

    def from_json_type(self, value):
        """Transform a value from a JSON object into the internal python type.

        For example, converts a JSON string "2019-08-30" into a python datetime.date object.

        .. warning:: When overwriting the type must be checked!
        """
        if value is None:
            return
        self.type_check_json(value)
        value = self._from_json_type(value)
        return value

    def decode_value(self, value):
        """Decode the value into a python object.

        .. note:: suitable for subclassing.
        """
        try:
            return self.syntax.parse(value)
        except valueError as exc:
            logger.debug(
                "ignoring invalid property %s value=%r is invalid: %s"
                % (self.property_name, value, exc),
            )
            return value

    def encode_value(self, value):
        """Encode the value into a UDM property value.

        .. note:: suitable for subclassing.
        """
        return self.syntax.parse(value)

    def _from_json_type(self, value):
        return value

    def _to_json_type(self, value):
        return value

    def type_check(self, value, types=None):
        """Checks if the value has the correct python type"""
        if not isinstance(value, types or self._python_types):
            must = (
                "%s (%s)" % (self._openapi_type, self._openapi_format)
                if self._openapi_format
                else "%s" % (self._openapi_type,)
            )
            actual = type(value).__name__
            logger.debug(
                "%r: Value=%r %r" % (self.property_name, value, type(self).__name__),
            )
            raise valueInvalidSyntax(_("Value must be of type %s not %s.") % (must, actual))

    def type_check_json(self, value):
        self.type_check(value, self._json_type)

    def type_check_subitems(self, value):
        pass

    def tostring(self, value):
        """A printable representation for e.g. the CLI or grid columns in UMC"""
        if self.property.multivalue:
            return [self.syntax.tostring(val) for val in value]
        else:
            return self.syntax.tostring(value)

    def parse_command_line(self, value):
        """Parse a string from the command line"""
        return self.syntax.parse_command_line(value)

    def get_openapi_definition(self):
        return {
            key: value
            for key, value in self.openapi_definition().items()
            if value is not None and value not in (float("inf"), -float("inf"))
        }

    def openapi_definition(self):
        definition = {
            "type": self._openapi_type,
        }
        if self._openapi_type in ("string", "number", "integer"):
            definition["format"] = self._openapi_format
        if self._openapi_type == "string":
            definition["pattern"] = self._openapi_regex
            definition["minLength"] = self._minimum
            definition["maxLength"] = self._maximum
        definition["example"] = self._openapi_example
        definition["readOnly"] = self._openapi_readonly
        definition["writeOnly"] = self._openapi_writeonly
        definition["nullable"] = self._openapi_nullable
        return definition

    def get_choices(self, lo, options):
        return self.syntax.get_choices(lo, options)

    def has_choices(self):
        opts = self.syntax.get_widget_options()
        return (
            opts.get("dynamicValues")
            or opts.get("staticValues")
            or opts.get("type") == "umc/modules/udm/MultiObjectSelect"
        )

    @classmethod
    def detect(cls, property, name):
        """Detect the :class:`univention.admin.types.TypeHint` type of a property automatically.

        We need this to be backwards compatible, with handlers, we don't influence.

        First considered is the `property.type_class` which can be explicit set in the module handler.

        Otherwise, it depends on wheather the field is multivalue or not:
        multivalue: A unordered :class:`Set` of `syntax.type_class` items
        singlevalue: `syntax.type_class` is used.
        """
        if property.type_class:
            return property.type_class(property, name)

        syntax = property.syntax() if inspect.isclass(property.syntax) else property.syntax
        type_class = syntax.type_class
        if not type_class:
            logger.debug(
                "Unknown type for property %r: %s" % (name, syntax.name),
            )
            type_class = cls

        if not property.multivalue:
            return type_class(property, name)
        else:
            if syntax.type_class_multivalue:
                return syntax.type_class_multivalue(property, name)

        # create a default type inheriting from a set
        # (LDAP attributes do not have a defined order - unless the "ordered" overlay module is activated and the attribute schema defines it)
        class MultivaluePropertyType(SetType):
            item_type = type_class

        return MultivaluePropertyType(property, name)


class StringType(TypeHint):
    _python_types = unicode  # type: _Types
    _encoding = "UTF-8"
    _openapi_type = "string"

    def decode_value(self, value):
        if isinstance(value, bytes):
            value = value.decode(self._encoding, "strict")
        return value


class DateType(StringType):
    """
    >>> x = DateType(univention.admin.property(syntax=univention.admin.syntax.string), 'a_date_time')
    >>> import datetime
    >>> now = datetime.date(2020, 1, 1)
    >>> x.to_json_type(now)  # doctest: +ALLOW_UNICODE
    '2020-01-01'
    """

    _python_types = datetime.date
    _json_type = unicode
    _openapi_format = "date"

    def decode_value(self, value):
        if value == "":
            return
        return self.syntax.to_datetime(value)

    def encode_value(self, value):
        return self.syntax.from_datetime(value)

    def _to_json_type(self, value):  # type: (datetime.date) -> unicode
        return unicode(value.isoformat())

    def _from_json_type(self, value):  # type: (unicode) -> datetime.date
        try:
            return datetime.date(*time.strptime(value, "%Y-%m-%d")[0:3])
        except ValueError:
            logger.debug("Wrong date format: %r" % (value,))
            raise valueInvalidSyntax(_('Date does not match format "%Y-%m-%d".'))
