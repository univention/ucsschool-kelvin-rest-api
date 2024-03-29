# -*- coding: utf-8 -*-
#
# UCS@school python lib: models
#
# Copyright 2014-2021 Univention GmbH
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
import inspect
import time
from copy import deepcopy
from functools import lru_cache
from typing import (  # noqa: F401
    Any,
    Callable,
    Dict,
    Iterable,
    List,
    Optional,
    Sequence,
    Set,
    Tuple,
    Type,
    TypeVar,
    Union,
)

import lazy_object_proxy
import ldap
from ldap.dn import escape_dn_chars
from ldap.filter import escape_filter_chars
from six import add_metaclass, iteritems

from udm_rest_client import UDM, NoObject as UdmNoObject, UdmModule, UdmObject
from univention.admin.filter import conjunction, expression
from univention.admin.uexceptions import noObject, noProperty, valueError, valueInvalidSyntax
from univention.admin.uldap import LoType, PoType, getAdminConnection, getMachineConnection

from ..pyhooks.pyhooks_loader import PyHooksLoader
from ..roles import all_roles, create_ucsschool_role_string
from ..schoolldap import SchoolSearchBase, name_from_dn
from .attributes import CommonName, Roles, SchoolAttribute, ValidationError
from .hook import KelvinHook
from .meta import UCSSchoolHelperMetaClass
from .utils import _, env_or_ucr, uldap_exists
from .validator import validate

SuperOrdinateType = Union[str, UdmObject]
UldapFilter = Union[str, conjunction, expression]
UCSSchoolModel = TypeVar("UCSSchoolModel", bound="UCSSchoolHelperAbstractClass")

PYHOOKS_PATH = "/var/lib/ucs-school-lib/kelvin-hooks"
PYHOOKS_BASE_CLASS = "ucsschool.lib.models.hook.Hook"
_pyhook_loader: PyHooksLoader = lazy_object_proxy.Proxy(
    lambda: PyHooksLoader(
        PYHOOKS_PATH, PYHOOKS_BASE_CLASS, filter_func=lambda x: issubclass(x, KelvinHook)
    )
)


class NoObject(noObject):
    def __init__(self, *args, dn: str = None, type: Type[UCSSchoolModel] = None) -> None:
        self.dn = dn
        self.type = type
        if not args:
            args = ("Could not find object of type {!r} with DN {!r}.".format(self.type, self.dn),)
        super(NoObject, self).__init__(*args)


class UnknownModel(NoObject):
    def __init__(self, dn: str, cls: Type[UCSSchoolModel]) -> None:
        self.dn = dn
        self.wrong_model = cls
        super(UnknownModel, self).__init__("No python class: %r is not a %s" % (dn, cls.__name__))


class WrongModel(NoObject):
    def __init__(self, dn: str, model: Type[UCSSchoolModel], wrong_model: Type[UCSSchoolModel]) -> None:
        self.dn = dn
        self.model = model
        self.wrong_model = wrong_model
        super(WrongModel, self).__init__(
            "Wrong python class: %r is not a %r but a %r" % (dn, wrong_model.__name__, model.__name__)
        )


class WrongObjectType(NoObject):
    def __init__(self, dn: str, cls: Type[UCSSchoolModel]) -> None:
        self.dn = dn
        self.wrong_model = cls
        super(WrongObjectType, self).__init__("Wrong objectClass: %r is not a %r." % (dn, cls.__name__))


class MultipleObjectsError(Exception):
    def __init__(self, objs: Sequence[UdmObject], *args, **kwargs) -> None:
        super(MultipleObjectsError, self).__init__(*args, **kwargs)
        self.objs = objs


class UDMPropertiesError(Exception):
    def __init__(self, message: str, *args, **kwargs):
        super(Exception, self).__init__(message, *args, **kwargs)
        self.message = message


@add_metaclass(UCSSchoolHelperMetaClass)
class UCSSchoolHelperAbstractClass(object):
    """
    Base class of all UCS@school models.
    Hides UDM.

    Attributes used for a class are defined like this::

        class MyModel(UCSSchoolHelperAbstractClass):
            my_attribute = Attribute('Label', required=True, udm_name='myAttr')

    From there on ``my_attribute=value`` may be passed to :py:meth:``__init__()``,
    ``my_model.my_attribute`` can be accessed and the value will be saved
    as ``obj['myAttr']`` in UDM when saving this instance.
    If an attribute of a base class is not wanted, it can be overridden::

        class MyModel(UCSSchoolHelperAbstractClass):
            school = None

    Meta information about the class are defined like this::

        class MyModel(UCSSchoolHelperAbstractClass):
            class Meta:
                udm_module = 'my/model'

    The meta information is then accessible in ``cls._meta``.

    Important functions:

        :py:meth:``__init__(**kwargs)``:
            kwargs should be the defined attributes

        :py:meth:``create(lo)``
            lo is an LDAP connection, specifically univention.admin.access.
            creates a new object. Returns False is the object already exists.
            And True after the creation

        :py:meth:``modify(lo)``
            modifies an existing object. Returns False if the object does not
            exist and True after the modification (regardless whether something
            actually changed or not)

        :py:meth:``remove(lo)``
            deletes the object. Returns False if the object does not exist and True
            after the deletion.

        :py:meth:``get_all(lo, school, filter_str, easy_filter=False)``
            classmethod; retrieves all objects found for this school. filter can be a string
            that is used to narrow down a search. Each property of the class' udm_module
            that is include_in_default_search is queried for that string.
            Example::

                User.get_all(lo, 'school', filter_str='name', easy_filter=True)

            will search in ``cn=users,ou=school,$base``
            for users/user UDM objects with ``|(username=*name*)(firstname=*name*)(...)`` and return
            User objects (not UDM objects)
            With ``easy_filter=False`` (default) it will use this very ``filter_str``

        :py:meth:``get_container(school)``
            a classmethod that points to the container where new instances are created
            and existing ones are searched.

        :py:meth:``dn``
            property, current distinguishable name of the instance. Calculated on the fly, it
            changes if instance.name or instance.school changes.
            ``instance.old_dn`` will be set to the original dn when the instance was created

        :py:meth:``get_udm_object(lo)``
            searches UDM for an entry that corresponds to ``self``. Normally uses the old_dn or dn.
            If ``cls._meta.name_is_unique`` then any object with ``self.name`` will match

        :py:meth:``exists(lo)``
            whether this object can be found in UDM.

        :py:meth:``from_udm_obj(udm_obj, school, lo)``
            classmethod; maps the info of ``udm_obj`` into a new instance (and sets ``school``)

        :py:meth:``from_dn(dn, school, lo)``
            finds dn in LDAP and uses ``from_udm_obj``

        :py:meth:``get_first_udm_obj(lo, filter_str)``
            returns the first found object of type ``cls._meta.udm_module`` that matches an
            arbitrary ``filter_str``

    More features:

    Validation:
        There are some auto checks built in: Attributes of the model that have a
        UDM syntax attached are validated against this syntax. Attributes that are
        required must be present.
        Attributes that are unlikely_to_change give a warning (not error) if the object
        already exists with other values.
        If the Meta information states that name_is_unique, the complete LDAP is searched
        for the instance's name before continuing.
        :py:meth:``validate()`` can be further customized.

    Hooks:
            # TODO: implement pyhooks
    """

    _cache: Dict[Tuple[str, Tuple[str, str]], UCSSchoolModel] = {}
    _search_base_cache: Dict[str, SchoolSearchBase] = {}
    _initialized_udm_modules: List[str] = []
    _attribute_udm_names: Dict[str, str] = None

    name: str = CommonName(_("Name"), aka=["Name"])
    school: str = SchoolAttribute(_("School"), aka=["School"])

    @classmethod
    def cache(cls, *args, **kwargs) -> UCSSchoolModel:
        """
        Initializes a new instance and caches it for subsequent calls.
        Useful when using School.cache(school_name) a lot in different
        functions, in loops, etc.
        """
        # TODO: rewrite function to have optional positional 'name' and 'school' arguments
        args = list(args)
        if args:
            kwargs["name"] = args.pop(0)
        if args:
            kwargs["school"] = args.pop(0)
        key = [cls.__name__] + [
            (k, kwargs[k]) for k in sorted(kwargs)
        ]  # TODO: rewrite: sorted(kwargs.items())
        key = tuple(key)
        if key not in cls._cache:
            obj = cls(**kwargs)
            cls._cache[key] = obj
        return cls._cache[key]

    @classmethod
    def invalidate_all_caches(cls) -> None:
        from ucsschool.lib.models.network import Network
        from ucsschool.lib.models.user import User
        from ucsschool.lib.models.utils import _pw_length_cache

        cls._cache.clear()
        # cls._search_base_cache.clear() # useless to clear
        _pw_length_cache.clear()
        Network._netmask_cache.clear()
        User._profile_path_cache.clear()
        User._samba_home_path_cache.clear()

    @classmethod
    def invalidate_cache(cls) -> None:
        keys_to_remove = [key for key in cls._cache.keys() if key[0] == cls.__name__]
        for key in keys_to_remove:
            del cls._cache[key]

    @classmethod
    def supports_school(cls) -> bool:
        return "school" in cls._attributes

    @classmethod
    def supports_schools(cls) -> bool:
        return "schools" in cls._attributes

    def __init__(self, name: str = None, school: str = None, **kwargs) -> None:
        """Initializes a new instance with kwargs.
        Not every kwarg is accepted, though: The name
        must be defined as a attribute at class level
        (or by a base class). All attributes are
        initialized at least with None
        Sets self.old_dn to self.dn, i.e. the name
        in __init__ will determine the old_dn, changing
        it after __init__ will result in trying to move the
        object!
        """
        self._udm_obj_searched = False
        self._udm_obj = None
        kwargs["name"] = name
        kwargs["school"] = school
        for key, attr in self._attributes.items():
            default = attr.value_default
            if callable(default):
                default = default()
            setattr(self, key, kwargs.get(key, default))
        self.__position = None
        self.old_dn = None
        self.old_dn = self.dn
        self.errors: Dict[str, List[str]] = {}
        self.warnings: Dict[str, List[str]] = {}
        self.udm_properties: Dict[str, Any] = {}
        self._in_hook = False  # if a hook is currently running

    @classmethod
    @lru_cache(maxsize=1)
    def get_admin_connection(cls) -> Tuple[LoType, PoType]:
        """get a cached ldap connection to the DC Master using this host's credentials"""
        return getAdminConnection()

    @classmethod
    @lru_cache(maxsize=1)
    def get_machine_connection(cls) -> Tuple[LoType, PoType]:
        """get a cached ldap connection to the DC Master using this host's credentials"""
        return getMachineConnection()

    @property
    def position(self) -> Optional[str]:
        if self.__position is None:
            return self.get_own_container()
        return self.__position

    @position.setter
    def position(self, position: str) -> None:
        if self.position != position:  # allow dynamic school changes until creation
            self.__position = position

    @property
    def dn(self) -> str:
        """Generates a DN where the lib would assume this
        instance to be. Changing name or school of self will most
        likely change the outcome of self.dn as well
        """
        if self.name and self.position:
            name = self.name
            return "%s=%s,%s" % (self._meta.ldap_name_part, escape_dn_chars(name), self.position)
        return self.old_dn

    def set_attributes(self, **kwargs) -> None:
        """
        A function to set the attributes of an UCS@school object in one function call.
        Only attributes that exist in self._attributes are set. The rest of the kwargs are
        simply ignored.

        :param kwargs: The attributes to set.
        """
        existing_attributes = self._attributes.keys()
        for key, value in kwargs.items():
            if key in existing_attributes:
                setattr(self, key, value)
            else:
                self.logger.debug(
                    "Setting attribute '{!r}' on {!r} does not work, since it doesn't exist.".format(
                        key, self
                    )
                )

    def set_dn(self, dn: str) -> None:
        """Does not really set dn, as this is generated
        on-the-fly. Instead, sets old_dn in case it was
        missed in the beginning or after create/modify/remove/move
        Also resets cached udm_obj as it may point to somewhere else
        """
        self._udm_obj_searched = False
        self.position = ldap.dn.dn2str(ldap.dn.str2dn(dn)[1:])
        self.old_dn = dn

    async def validate(self, lo: UDM, validate_unlikely_changes: bool = False) -> None:
        from ucsschool.lib.models.school import School

        self.errors.clear()
        self.warnings.clear()
        for name, attr in iteritems(self._attributes):
            value = getattr(self, name)
            try:
                attr.validate(value)
            except ValueError as e:
                self.add_error(name, str(e))
        if self._meta.name_is_unique and not self._meta.allow_school_change:
            if await self.exists_outside_school(lo):
                self.add_error(
                    "name",
                    _(
                        "The name is already used somewhere outside the school. It may not be taken "
                        "twice and has to be changed."
                    ),
                )
        if self.supports_school() and self.school:
            if not await School.cache(self.school).exists(lo):
                self.add_error(
                    "school",
                    _('The school "%s" does not exist. Please choose an existing one or create it.')
                    % self.school,
                )
        await self.validate_roles(lo)
        if validate_unlikely_changes:
            if await self.exists(lo):
                udm_obj = await self.get_udm_object(lo)
                try:
                    original_self = await self.from_udm_obj(udm_obj, self.school, lo)
                except (UnknownModel, WrongModel):
                    pass
                else:
                    for name, attr in iteritems(self._attributes):
                        if attr.unlikely_to_change:
                            new_value = getattr(self, name)
                            old_value = getattr(original_self, name)
                            if new_value and old_value:
                                if new_value != old_value:
                                    self.add_warning(
                                        name,
                                        _("The value changed from %(old)s. This seems unlikely.")
                                        % {"old": old_value},
                                    )

    async def validate_roles(self, lo: UDM) -> None:
        pass

    def add_warning(self, attribute: str, warning_message: str) -> None:
        warnings = self.warnings.setdefault(attribute, [])
        if warning_message not in warnings:
            warnings.append(warning_message)

    def add_error(self, attribute: str, error_message: str) -> None:
        errors = self.errors.setdefault(attribute, [])
        if error_message not in errors:
            errors.append(error_message)

    @classmethod
    def _ldap_filter(cls, name: str) -> str:
        if not cls._meta._ldap_filter:
            raise TypeError(f"No '_ldap_filter' defined for class {cls.__name__}.")
        return cls._meta._ldap_filter.format(name=escape_filter_chars(name))

    async def exists(self, lo: UDM) -> bool:
        name = self.get_name_from_dn(self.old_dn or self.dn) or self.name
        if not name:
            return False
        if self._meta._ldap_filter:
            return uldap_exists(self._ldap_filter(name=name))
        return await self.get_udm_object(lo) is not None

    async def exists_outside_school(self, lo: UDM) -> bool:
        if not self.supports_school():
            return False
        from ucsschool.lib.models.school import School

        udm_obj = await self.get_udm_object(lo)
        if udm_obj is None:
            return False
        return not udm_obj.dn.lower().endswith(School.cache(self.school).dn.lower())

    async def _call_pyhooks(self, hook_time: str, func_name: str, udm: UDM) -> None:
        """
        Run Python based hooks (`*.py` files in `/usr/share/u-s-i/pyhooks`
        containing a subclass of :py:class:`ucsschool.lib.models.hook.Hook`).

        :param str hook_time: `pre` or `post`
        :param str func_name: `create`, `modify`, `move` or `remove`
        :param lo: UDM REST Client instance
        :return: None
        :rtype: None
        """
        self._in_hook = True
        lo, _ = self.get_admin_connection()
        all_hooks = _pyhook_loader.get_hook_objects(udm=udm, lo=lo)
        meth_name = "{}_{}".format(hook_time, func_name)
        try:
            for func in all_hooks.get(meth_name, []):  # type: Callable[..., Any]
                if issubclass(self.__class__, func.__self__.model):
                    func_py_name = f"{func.__self__.__class__.__name__}.{func.__name__}"
                    self.logger.debug(
                        "Running %s hook %s for %s...",
                        meth_name,
                        func_py_name,
                        self,
                    )
                    if not inspect.iscoroutinefunction(func):
                        raise TypeError(f"Hook method {func_py_name} must be an async function.")
                    func.__self__.udm = udm  # update UDM instance to the current one
                    await func(self)
        finally:
            self._in_hook = False

    async def call_hooks(self, udm: UDM, hook_time: str, func_name: str) -> Optional[bool]:
        """
        Calls Python based hooks (*.py files in /usr/share/u-s-i/pyhooks).

        In the case of `post`, this method is only called, if the corresponding
        function (`create()`, `modify()`, `move()` or `remove()`) returned
        `True`.

        :param str hook_time: `pre` or `post`
        :param str func_name: `create`, `modify`, `move` or `remove`
        :param udm: UDM REST Client instance
        :return: `or`d return value of legacy hooks or True if no hook ran
        :rtype: bool: `or`d return value of legacy hooks or True if no hook ran
        """
        self.logger.debug(
            "Starting %s.call_hooks(%r, %r) for %r.",
            self.__class__.__name__,
            hook_time,
            func_name,
            self,
        )
        t0 = time.time()
        await self._call_pyhooks(hook_time, func_name, udm)
        self.logger.debug(
            "Timings self._call_pyhooks(%r, %r): %.3f", hook_time, func_name, time.time() - t0
        )

    def build_hook_line(self, hook_time, func_name):  # type: (str, str) -> Optional[str]
        """Must be overridden if the model wants to support hooks.
        Do so by something like:
        return self._build_hook_line(self.attr1, self.attr2, 'constant')
        """
        return None

    @classmethod
    def hook_init(cls, hook):  # type: (PYHOOKS_BASE_CLASS) -> None
        """
        Overwrite this method to add individual initialization code to all
        hooks of a ucsschool.lib.model class.
        (See `.SchoolClass.hook_init()` for an example.)

        :param hook: instance of a subclass of :py:class:`ucsschool.lib.model.hook.Hook`
        :return: None
        :rtype: None
        """
        pass

    @classmethod
    def attribute_udm_names(cls) -> Dict[str, str]:
        if not cls._attribute_udm_names:
            cls._attribute_udm_names = dict(
                (attr.udm_name, name) for name, attr in cls._attributes.items() if attr.udm_name
            )
        return cls._attribute_udm_names

    def _prevent_mapped_attributes_in_udm_properties(self):  # type: () -> None
        """
        Make sure users do not store values for ucsschool.lib mapped Attributes
        in udm_properties.
        """
        if not self.udm_properties:
            return

        bad_props = set(self.udm_properties.keys()).intersection(self.attribute_udm_names())
        if bad_props:
            raise UDMPropertiesError(
                "UDM properties '{}' must be set as attributes of the {} object (not in "
                "udm_properties).".format("', '".join(bad_props), self.__class__.__name__)
            )

    def _handle_udm_properties(self, udm_obj: UdmObject):
        """
        This method sets the values in self.udm_properties directly in the udm object.
        """
        for property_, value in (self.udm_properties or {}).items():
            try:
                udm_obj.props[property_] = value
            except (KeyError, noProperty) as exc:
                raise UDMPropertiesError(
                    "UDM property '{}' could not be set. {}: {}".format(
                        property_, exc.__class__.__name__, exc
                    )
                )
            except (valueError, valueInvalidSyntax) as exc:
                raise UDMPropertiesError(
                    "UDM property '{}' could not be set. {}: {}".format(
                        property_, exc.__class__.__name__, exc
                    )
                )
            except Exception as exc:
                self.logger.exception(
                    "Unexpected exception caught: UDM property %r could not be set for object %r",
                    property_,
                    self,
                    exc,
                )
                raise UDMPropertiesError(
                    "UDM property {!r} could not be set. {}: {}".format(
                        property_, exc.__class__.__name__, exc
                    )
                )

    async def _alter_udm_obj(self, udm_obj: UdmObject) -> None:
        self._prevent_mapped_attributes_in_udm_properties()
        for name, attr in iteritems(self._attributes):
            if attr.udm_name:
                value = getattr(self, name)
                if attr.map_to_udm:
                    setattr(udm_obj.props, attr.udm_name, value)
        # TODO: move g[s]et_default_options() from User here to update udm_obj.options
        self._handle_udm_properties(udm_obj)

    async def create(self, lo: UDM, validate: bool = True) -> bool:
        """
        Creates a new UDM instance.
        Calls pre-hooks.
        If the object already exists, returns False.
        If the object does not yet exist, creates it, returns True and
        calls post-hooks.
        """
        if self._in_hook:
            # prevent recursion
            self.logger.warning(
                "Running create() from within a hook, skipping hook execution. Please use "
                "create_without_hooks() from within hooks."
            )
        else:
            await self.call_hooks(hook_time="pre", func_name="create", udm=lo)

        t0 = time.time()
        success = await self.create_without_hooks(lo, validate)  # TODO: this takes 680 ms
        self.logger.debug("Timings self.create_without_hooks(): %.3f", time.time() - t0)
        if success and not self._in_hook:
            await self.call_hooks(hook_time="post", func_name="create", udm=lo)

        return success

    async def create_without_hooks(self, lo: UDM, validate: bool) -> bool:
        t0 = time.time()
        if await self.exists(lo):
            return False
        self.logger.info("Creating %r", self)
        await self.create_without_hooks_roles(lo)
        if validate:
            await self.validate(lo)  # TODO: this takes 100 ms
            if self.errors:
                raise ValidationError(self.errors.copy())
        t1 = time.time()
        pos = PoType(env_or_ucr("ldap/base"))
        container = self.position
        if not container:
            self.logger.error("%r cannot determine a container. Unable to create!", self)
            return False
        try:
            pos.setDn(container)
            superordinate_obj = await self.get_superordinate(lo)
            if superordinate_obj:  # TODO: fix UDM REST API client
                superordinate_arg = superordinate_obj._api_obj
            else:
                superordinate_arg = None
            t2 = time.time()
            # TODO: this takes 240 ms:
            udm_obj = await lo.get(self._meta.udm_module).new(superordinate=superordinate_arg)
            t3 = time.time()
            if not udm_obj.superordinate:
                # TODO: remove this, once new() has been fixed
                udm_obj.superordinate = superordinate_obj
            udm_obj.position = pos.getDn()
            # here is the real logic
            await self.do_create(udm_obj, lo)  # TODO: this takes 680 ms (of which UDM REST took 650 ms)
            t4 = time.time()

            # get it fresh from the database (needed for udm_obj._exists ...)
            self.set_dn(self.dn)
            self.logger.info("%r successfully created", self)
            self.logger.debug(
                "Timings: t1=%.3f t2=%.3f t3=%.3f t4=%.3f",
                t1 - t0,
                t2 - t1,
                t3 - t2,
                t4 - t3,
            )
            return True
        finally:
            t5 = time.time()
            self.invalidate_cache()
            self.logger.debug("Timings self.invalidate_cache(): %.3f", time.time() - t5)

    async def create_without_hooks_roles(self, lo: UDM) -> None:
        """
        Run by py:meth:`create_without_hooks()` before py:meth:`validate()`
        (and thus before py:meth:`do_create()`).
        """
        pass

    async def do_create(self, udm_obj: UdmObject, lo: UDM) -> None:
        """Actual udm_obj manipulation. Override this if
        you want to further change values of udm_obj, e.g.
        def do_create(self, udm_obj, lo):
            udm_obj['used_in_ucs_school'] = '1'
            super(MyModel, self).do_create(udm_obj, lo)
        """
        t0 = time.time()
        await self._alter_udm_obj(udm_obj)
        t1 = time.time()
        await udm_obj.save()  # TODO: this takes 680 ms
        t2 = time.time()
        self.logger.debug("Timings: t1=%.3f t2=%.3f", t1 - t0, t2 - t1)

    async def modify(self, lo: UDM, validate: bool = True, move_if_necessary: bool = None) -> bool:
        """
        Modifies an existing UDM instance.
        Calls pre-hooks.
        If the object does not exist, returns False.
        If the object exists, modifies it, returns True and
        calls post-hooks.
        """
        if self._in_hook:
            # prevent recursion
            self.logger.warning(
                "Running modify() from within a hook, skipping hook execution. Please use "
                "modify_without_hooks() from within hooks."
            )
        else:
            await self.call_hooks(hook_time="pre", func_name="modify", udm=lo)

        success = await self.modify_without_hooks(lo, validate, move_if_necessary)
        if success and not self._in_hook:
            await self.call_hooks(hook_time="post", func_name="modify", udm=lo)
        return success

    async def modify_without_hooks(
        self, lo: UDM, validate: bool = True, move_if_necessary: bool = None
    ) -> bool:
        self.logger.info("Modifying %r", self)

        if move_if_necessary is None:
            move_if_necessary = self._meta.allow_school_change

        self.update_ucsschool_roles()

        if validate:
            await self.validate(lo, validate_unlikely_changes=True)
            if self.errors:
                raise ValidationError(self.errors.copy())

        udm_obj = await self.get_udm_object(lo)
        if not udm_obj:
            self.logger.info("%s does not exist!", self.old_dn)
            return False

        try:
            old_attrs = deepcopy(udm_obj.props)
            await self.modify_without_hooks_roles(udm_obj)
            await self.do_modify(udm_obj, lo)
            # get it fresh from the database
            self.set_dn(self.dn)
            udm_obj = await self.get_udm_object(lo)
            same = old_attrs == deepcopy(udm_obj.props)
            if move_if_necessary:
                if udm_obj.dn != self.dn:
                    if await self.move_without_hooks(lo, udm_obj, force=True):
                        same = False
            if same:
                self.logger.info("%r not modified. Nothing changed", self)
            else:
                self.logger.info("%r successfully modified", self)
            # return not same
            return True
        finally:
            self.invalidate_cache()

    async def modify_without_hooks_roles(self, udm_obj: UdmObject) -> bool:
        """Run by py:meth:`modify_without_hooks()` before py:meth:`do_modify()`."""
        pass

    def update_ucsschool_roles(self) -> None:
        """Run by py:meth:`modify_without_hooks()` before py:meth:`validate()`."""
        pass

    async def do_modify(self, udm_obj: UdmObject, lo: UDM) -> None:
        """
        Actual udm_obj manipulation. Override this if
        you want to further change values of udm_obj, e.g.
        def do_modify(self, udm_obj, lo):
            udm_obj['used_in_ucs_school'] = '1'
            super(MyModel, self).do_modify(udm_obj, lo)
        """
        await self._alter_udm_obj(udm_obj)
        await udm_obj.save()

    async def move(self, lo: UDM, udm_obj: UdmObject = None, force: bool = False) -> bool:
        if self._in_hook:
            # prevent recursion
            self.logger.warning(
                "Running move() from within a hook, skipping hook execution. Please use "
                "move_without_hooks() from within hooks."
            )
        else:
            await self.call_hooks(hook_time="pre", func_name="move", udm=lo)
        success = await self.move_without_hooks(lo, udm_obj, force)
        if success and not self._in_hook:
            await self.call_hooks(hook_time="post", func_name="move", udm=lo)
        return success

    async def move_without_hooks(self, lo: UDM, udm_obj: UdmObject = None, force: bool = False) -> bool:
        if udm_obj is None:
            udm_obj = await self.get_udm_object(lo)
        if udm_obj is None:
            self.logger.warning("No UDM object found to move from (%r)", self)
            return False
        if self.supports_school() and await self.get_school_obj(lo) is None:
            self.logger.warning("%r wants to move itself to a not existing school", self)
            return False
        self.logger.info("Moving %r to %r", udm_obj.dn, self)
        if udm_obj.dn == self.dn:
            self.logger.warning("%r wants to move to its own DN!", self)
            return False
        if force or self._meta.allow_school_change:
            try:
                await self.do_move(udm_obj, lo)
            finally:
                self.invalidate_cache()
            self.set_dn(self.dn)
        else:
            self.logger.warning("Would like to move %s to %r. But it is not allowed!", udm_obj.dn, self)
            return False
        return True

    async def do_move(self, udm_obj: UdmObject, lo: UDM) -> None:
        old_school, new_school = self.get_school_from_dn(self.old_dn), self.get_school_from_dn(self.dn)
        udm_obj.position = self.position
        setattr(udm_obj.props, self._attributes["name"].udm_name, self.name)
        await udm_obj.save()
        if self.supports_school() and old_school and old_school != new_school:
            await self.do_school_change(udm_obj, lo, old_school)
            await self.do_move_roles(udm_obj, lo, old_school, new_school)

    async def do_move_roles(self, udm_obj: UdmObject, lo: UDM, old_school: str, new_school: str) -> None:
        self.update_ucsschool_roles()

    async def change_school(self, school: str, lo: UDM) -> bool:
        if self.school in self.schools:
            self.schools.remove(self.school)
        if school not in self.schools:
            self.schools.append(school)
        self.school = school
        self.position = self.get_own_container()
        return await self.move(lo, force=True)

    async def do_school_change(self, udm_obj: UdmObject, lo: UDM, old_school: str) -> None:
        self.logger.info("Going to move %r from school %r to %r", self.old_dn, old_school, self.school)

    async def remove(self, lo: UDM) -> bool:
        """
        Removes an existing UDM instance.
        Calls pre-hooks.
        If the object does not exist, returns False.
        If the object exists, removes it, returns True and
        calls post-hooks.
        """
        if self._in_hook:
            # prevent recursion
            self.logger.warning(
                "Running remove() from within a hook, skipping hook execution. Please use "
                "remove_without_hooks() from within hooks."
            )
        else:
            await self.call_hooks(hook_time="pre", func_name="remove", udm=lo)
        success = await self.remove_without_hooks(lo)
        if success and not self._in_hook:
            await self.call_hooks(hook_time="post", func_name="remove", udm=lo)
        return success

    async def remove_without_hooks(self, lo: UDM) -> bool:
        self.logger.info("Deleting %r", self)
        udm_obj = await self.get_udm_object(lo)
        if udm_obj:
            try:
                await udm_obj.delete()
                self.set_dn(None)
                self.logger.info("%r successfully removed", self)
                return True
            finally:
                self.invalidate_cache()
        self.logger.info("%r does not exist!", self)
        return False

    @classmethod
    def get_name_from_dn(cls, dn: str) -> str:
        if dn:
            try:
                name = name_from_dn(dn)
            except ldap.DECODING_ERROR:
                name = ""
            return name

    @classmethod
    def get_school_from_dn(cls, dn: str) -> str:
        return SchoolSearchBase.getOU(dn)

    @classmethod
    def find_field_label_from_name(cls, field: str) -> str:
        for name, attr in cls._attributes.items():
            if name == field:
                return attr.label

    def get_error_msg(self) -> str:
        return self.create_validation_msg(iteritems(self.errors))

    def get_warning_msg(self) -> str:
        return self.create_validation_msg(iteritems(self.warnings))

    def create_validation_msg(self, items: Iterable[Tuple[str, List[str]]]) -> str:
        validation_msg = ""
        for key, msg in items:
            label = self.find_field_label_from_name(key)
            msg_str = ""
            for error in msg:
                msg_str += error
                if not (error.endswith("!") or error.endswith(".")):
                    msg_str += "."
                msg_str += " "
            validation_msg += "%s: %s" % (label, msg_str)
        return validation_msg[:-1]

    async def get_udm_object(self, lo: UDM) -> Optional[UdmObject]:
        """
        Returns the UDM object that corresponds to self.
        If self._meta.name_is_unique it searches for any UDM object
        with self.name.
        If not (which is the default) it searches for self.old_dn or self.dn
        Returns None if no object was found. Caches the result, even None
        If you want to re-search, you need to explicitely set
        self._udm_obj_searched = False
        """
        if self._udm_obj_searched is False or self._udm_obj is None:
            dn = self.old_dn or self.dn
            superordinate = await self.get_superordinate(lo)
            if dn is None:
                self.logger.error("Getting %s UDM object: No DN!", self.__class__.__name__)
                return None
            if self._meta.name_is_unique:
                if self.name is None:
                    self.logger.error('Getting %s UDM object: Empty "name"!', self.__class__.__name__)
                    return None
                udm_name = self._attributes["name"].udm_name
                name = self.get_name_from_dn(dn)
                filter_str = "%s=%s" % (udm_name, escape_filter_chars(name))
                self._udm_obj = await self.get_first_udm_obj(lo, filter_str, superordinate)
                if self._udm_obj:
                    validate(self._udm_obj, self.logger)
            else:
                self.logger.debug("Getting %s UDM object by dn: %s", self.__class__.__name__, dn)
                try:
                    self._udm_obj = await lo.get(self._meta.udm_module).get(dn)
                except UdmNoObject:
                    self._udm_obj = None
                else:
                    validate(self._udm_obj, self.logger)
            self._udm_obj_searched = True
        return self._udm_obj

    async def get_school_obj(self, lo: UDM) -> Optional[UCSSchoolModel]:
        from ucsschool.lib.models.school import School

        if not self.supports_school():
            return None
        school = School.cache(self.school)
        try:
            return await School.from_dn(school.dn, None, lo)
        except noObject:
            self.logger.warning("%r does not exist!", school)
            return None

    async def get_superordinate(self, lo: UDM) -> Optional[SuperOrdinateType]:
        return None

    def get_own_container(self) -> Optional[str]:
        if self.supports_school() and not self.school:
            return None
        return self.get_container(self.school)

    @classmethod
    def get_container(cls, school: str) -> str:
        """
        raises NotImplementedError by default. Needs to be overridden!
        """
        raise NotImplementedError("%s.get_container()" % (cls.__name__,))

    @classmethod
    def get_search_base(cls, school_name: str) -> SchoolSearchBase:
        from ucsschool.lib.models.school import School

        if school_name not in cls._search_base_cache:
            school = School(name=school_name)
            cls._search_base_cache[school_name] = SchoolSearchBase([school.name], dn=school.dn)
        return cls._search_base_cache[school_name]

    @classmethod
    async def get_all(
        cls,
        lo: UDM,
        school: str = None,
        filter_str: str = None,
        easy_filter: str = False,
        superordinate: SuperOrdinateType = None,
    ) -> List[UCSSchoolModel]:
        """
        Returns a list of all objects that can be found in cls.get_container() with the
        correct udm_module
        If filter_str is given, all udm properties with include_in_default_search are
        queried for that string (so that it should be the value)
        """
        complete_filter = cls._meta.udm_filter
        if complete_filter and not complete_filter.startswith("("):
            complete_filter = "({})".format(complete_filter)
        if easy_filter:
            filter_from_filter_str = cls.build_easy_filter(filter_str)
        else:
            filter_from_filter_str = filter_str
            if filter_from_filter_str and not filter_from_filter_str.startswith("("):
                filter_from_filter_str = "({})".format(filter_from_filter_str)
        if filter_from_filter_str:
            if complete_filter:
                complete_filter = conjunction("&", [complete_filter, filter_from_filter_str])
            else:
                complete_filter = filter_from_filter_str
        complete_filter = str(complete_filter)
        cls.logger.debug("Getting all %s of %s with filter %r", cls.__name__, school, complete_filter)
        ret = []
        t0 = time.time()
        for udm_obj in await cls.lookup(lo, school, complete_filter, superordinate=superordinate):
            try:
                ret.append(await cls.from_udm_obj(udm_obj, school, lo))
            except NoObject:
                continue
        cls.logger.debug("Timings: retrieved %d objects in %.3f sec.", len(ret), time.time() - t0)
        return ret

    @classmethod
    async def lookup(
        cls, lo: UDM, school: str, filter_s: UldapFilter = "", superordinate: SuperOrdinateType = None
    ) -> List[UdmObject]:  # TODO: make this a generator?
        try:
            return [
                obj
                async for obj in lo.get(cls._meta.udm_module).search(
                    filter_s=filter_s, base=cls.get_container(school), scope="sub"
                )
            ]
        except UdmNoObject as exc:
            cls.logger.warning(
                "Error while getting all %s of %s (probably %r does not exist): %s",
                cls.__name__,
                school,
                cls.get_container(school),
                exc,
            )
            return []

    @classmethod
    def _attrs_for_easy_filter(cls) -> List[str]:
        raise NotImplementedError("No access to low level UDM property information.")

    @classmethod
    def build_easy_filter(cls, filter_str: str) -> UldapFilter:
        def escape_filter_chars_exc_asterisk(value: str) -> str:
            value = ldap.filter.escape_filter_chars(value)
            value = value.replace(r"\2a", "*")
            return value

        if filter_str:
            filter_str = escape_filter_chars_exc_asterisk(filter_str)
            expressions = []
            for key in cls._attrs_for_easy_filter():
                expressions.append(expression(key, filter_str))
            if expressions:
                return conjunction("|", expressions)

    @classmethod
    async def from_udm_obj(cls, udm_obj: UdmObject, school: str, lo: UDM) -> UCSSchoolModel:
        """
        Creates a new instance with attributes of the udm_obj.
        Uses get_class_for_udm_obj()
        """
        # Design fault. school is part of the DN or the ucsschoolSchool attribute.
        klass = await cls.get_class_for_udm_obj(udm_obj, school)
        if klass is None:
            cls.logger.warning(
                "UDM object %r does not correspond to a Python class in the UCS school lib.", udm_obj.dn
            )
            raise UnknownModel(udm_obj.dn, cls)
        if klass is not cls:
            cls.logger.debug(
                "UDM object %s is not %s, but actually %s", udm_obj.dn, cls.__name__, klass.__name__
            )
            if not issubclass(klass, cls):
                # security!
                # ExamStudent must not be converted into Teacher/Student/etc.,
                # SchoolClass must not be converted into ComputerRoom
                # while Group must be converted into ComputerRoom, etc. and User must be converted into
                # Student, etc.
                raise WrongModel(udm_obj.dn, klass, cls)
            return await klass.from_udm_obj(udm_obj, school, lo)
        validate(udm_obj, cls.logger)
        attrs = {
            "school": cls.get_school_from_dn(udm_obj.dn) or school
        }  # TODO: is this adjustment okay?
        if cls.supports_schools():
            attrs["schools"] = udm_obj.props.school
        for name, attr in iteritems(cls._attributes):
            if attr.udm_name:
                udm_value = getattr(udm_obj.props, attr.udm_name)
                if udm_value == "":
                    udm_value = None
                attrs[name] = udm_value
        obj = cls(**deepcopy(attrs))
        obj.set_dn(udm_obj.dn)
        obj._udm_obj_searched = True
        obj._udm_obj = udm_obj
        return obj

    @classmethod
    async def get_class_for_udm_obj(
        cls, udm_obj: UdmObject, school: str
    ) -> Optional[Type[UCSSchoolModel]]:
        """
        Returns cls by default.

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
        """
        return cls

    def __repr__(self) -> str:
        dn = self.dn
        dn = "%r, old_dn=%r" % (dn, self.old_dn) if dn != self.old_dn else repr(dn)
        if self.supports_school():
            return "%s(name=%r, school=%r, dn=%s)" % (
                self.__class__.__name__,
                self.name,
                self.school,
                dn,
            )
        else:
            return "%s(name=%r, dn=%s)" % (self.__class__.__name__, self.name, dn)

    def __lt__(self, other: UCSSchoolModel) -> bool:
        return self.name < other.name

    @classmethod
    async def from_dn(
        cls, dn: str, school: str, lo: UDM, superordinate: SuperOrdinateType = None
    ) -> UCSSchoolModel:
        """
        Returns a new instance based on the UDM object found at dn
        raises noObject if the udm_module does not match the dn
        or dn is not found
        """
        if school is None and cls.supports_school():
            school = cls.get_school_from_dn(dn)
            if school is None:
                cls.logger.warning("Unable to guess school from %r", dn)
        try:
            cls.logger.debug("Looking up %s with dn %r", cls.__name__, dn)
            mod: UdmModule = lo.get(cls._meta.udm_module)
            udm_obj: UdmObject = await mod.get(dn)
            return await cls.from_udm_obj(udm_obj, school, lo)
        except UdmNoObject as exc:
            raise NoObject(dn=dn, type=cls.__name__) from exc
        except IndexError:
            # happens when cls._meta.udm_module does not "match" the dn
            raise WrongObjectType(dn, cls)

    @classmethod
    async def get_only_udm_obj(
        cls, lo: UDM, filter_str: str = None, superordinate: str = None, base: str = None
    ) -> Optional[UdmObject]:
        """
        Returns the one UDM object of class cls._meta.udm_module that
        matches a given filter.
        If more than one is found, a MultipleObjectsError is raised
        If none is found, None is returned
        """
        if cls._meta.udm_filter:
            udm_filter = cls._meta.udm_filter
            if not udm_filter.startswith("("):
                udm_filter = f"({udm_filter})"
            filter_str = f"(&{udm_filter}({filter_str}))"
        cls.logger.debug("Getting %s UDM object by filter: %s", cls.__name__, filter_str)
        objs = [
            obj
            async for obj in lo.get(cls._meta.udm_module).search(
                filter_s=str(filter_str), base=base or env_or_ucr("ldap/base"), scope="sub"
            )
        ]
        if len(objs) == 0:
            return None
        if len(objs) > 1:
            raise MultipleObjectsError(objs=objs)
        obj = objs[0]
        validate(obj, cls.logger)
        return obj

    @classmethod
    async def get_first_udm_obj(
        cls, lo: UDM, filter_str: str, superordinate: SuperOrdinateType = None
    ) -> Optional[UdmObject]:
        """
        Returns the first UDM object of class cls._meta.udm_module that
        matches a given filter
        """
        try:
            return await cls.get_only_udm_obj(lo, filter_str, superordinate)
        except MultipleObjectsError as exc:
            obj = exc.objs[0]
            validate(obj, cls.logger)
            return obj

    @classmethod
    async def find_udm_superordinate(cls, dn: str, lo: UDM) -> Optional[SuperOrdinateType]:
        obj = await lo.get(cls._meta.udm_module).get(dn)
        return obj.superordinate

    def to_dict(self) -> Dict[str, Any]:
        """
        Returns a dictionary somewhat representing this instance.
        This dictionary is usually used when sending the instance to
        a browser as JSON.
        By default the attributes are present as well as the dn and
        the udm_module.
        """
        ret = {"$dn$": self.dn, "objectType": self._meta.udm_module}
        for name, attr in iteritems(self._attributes):
            if not attr.internal:
                ret[name] = getattr(self, name)
        return ret

    def __deepcopy__(self, memo: Dict[int, Any]) -> UCSSchoolModel:
        id_self = id(self)
        if not memo.get(id_self):
            memo[id_self] = self.__class__(**self.to_dict())
        return memo[id_self]

    def _map_func_name_to_code(self, func_name: str) -> str:
        if func_name == "create":
            return "A"
        elif func_name == "modify":
            return "M"
        elif func_name == "remove":
            return "D"
        elif func_name == "move":
            return "MV"


class RoleSupportMixin(object):
    """
    Attribute and methods to handle the `ucsschool_roles` / `ucsschoolRoles`
    attribute.
    """

    ucsschool_roles: List[str] = Roles(_("Roles"), aka=["Roles"])

    default_roles: List[str] = []
    _school_in_name = False
    _school_in_name_prefix = False

    def get_schools(self) -> Set[str]:
        return set(getattr(self, "schools", []) + [self.school])

    async def get_schools_from_udm_obj(self, udm_obj: UdmObject) -> List[str]:
        if self._school_in_name:
            return [udm_obj.props.name]
        elif self._school_in_name_prefix:
            try:
                return [udm_obj.props.name.split("-", 1)[0]]
            except KeyError:
                return []
        else:
            try:
                return udm_obj.props.school
            except AttributeError as exc:
                self.logger.exception(
                    "AttributeError in RoleSupportMixin.get_schools_from_udm_obj(%r): %s", udm_obj, exc
                )
                raise

    @property
    def roles_as_dicts(self) -> List[Dict[str, str]]:
        """Get :py:attr:`self.ucsschool_roles` as a dict."""
        res = []
        for role in self.ucsschool_roles:
            m = Roles.syntax.regex.match(role)
            if m:
                res.append(m.groupdict())
        return res

    @roles_as_dicts.setter
    def roles_as_dicts(self, roles: Iterable[Dict[str, str]]) -> None:
        """
        Take dict from :py:attr:`roles_as_dicts` and write to
        :py:attr:`self.ucsschool_roles`.
        """
        self.ucsschool_roles = ["{role}:{context_type}:{context}".format(**role) for role in roles]

    async def do_move_roles(self, udm_obj: UdmObject, lo: UDM, old_school: str, new_school: str) -> None:
        old_roles = list(self.ucsschool_roles)
        # remove all roles of old school
        school_roles = [
            role
            for role in self.roles_as_dicts
            if role["context"] != old_school and role["context_type"] == "school"
        ]
        # do not apply faulty roles with context_type = school
        school_roles = [role for role in school_roles if role in all_roles]
        non_school_roles = [
            role
            for role in self.roles_as_dicts
            if role["context"] != old_school and role["context_type"] != "school"
        ]
        # only add role(s) if object has no roles in new school
        if all(role["context"] != new_school for role in school_roles):
            # add only role(s) of current Python class in new school
            school_roles.extend(
                [
                    {"context": new_school, "context_type": "school", "role": role}
                    for role in self.default_roles
                ]
            )
        self.roles_as_dicts = school_roles + non_school_roles
        if old_roles != self.ucsschool_roles:
            self.logger.info("Updating roles: %r -> %r...", old_roles, self.ucsschool_roles)
            # cannot use do_modify() here, as it would delete the old object
            lo_admin, po = self.get_admin_connection()
            lo_admin.modify(
                self.dn,
                [
                    (
                        "ucsschoolRole",
                        [r.encode("utf-8") for r in old_roles],
                        [r.encode("utf-8") for r in self.ucsschool_roles],
                    )
                ],
            )

    async def validate_roles(self, lo: UDM) -> None:
        # for now different roles in different schools are not supported
        schools = self.get_schools()
        for role in self.roles_as_dicts:
            if role["context_type"] != "school":
                # check only context_type == 'school' for now
                continue
            if role["context"] != "-" and role["context"] not in schools:
                self.add_error(
                    "ucsschool_roles",
                    _(
                        "Context {role}:{context_type}:{context} is not allowed for {dn}. Object is not "
                        "in that school."
                    ).format(dn=self.dn, **role),
                )

    async def create_without_hooks_roles(self, lo: UDM) -> None:
        """
        Run by py:meth:`create_without_hooks()` before py:meth:`validate()`
        (and thus before py:meth:`do_create()`).
        """
        roles = self.roles_as_dicts
        if self.default_roles and not any(role["context"] for role in roles if role["context"] != "-"):
            schools = self.get_schools()
            self.ucsschool_roles += [
                create_ucsschool_role_string(role, school)
                for role in self.default_roles
                for school in schools
            ]

    def update_ucsschool_roles(self) -> None:
        """
        Run by py:meth:`modify_without_hooks()` before py:meth:`validate()`.

        Add :py:attr:`ucsschool_roles` entries of `context_type=school` to
        object, if it got new/additional school(s) and object has no role(s)
        in those yet.

        Delete :py:attr:`ucsschool_roles` entries of `context_type=school` of
        object, if it was removed from school(s).
        """
        roles = self.roles_as_dicts
        old_schools = set(role["context"] for role in roles if role["context"] != "-")
        cur_schools = set(self.get_schools())
        new_schools = cur_schools - old_schools
        removed_schools = old_schools - cur_schools
        for new_school in new_schools:
            # only add role(s) if object has no roles in new school
            if any(role["context"] == new_school for role in roles):
                continue
            # add only role(s) of current Python class in new school
            roles.extend(
                {"context": new_school, "context_type": "school", "role": role}
                for role in self.default_roles
            )
        for role in deepcopy(roles):
            if role["context_type"] == "school" and role["context"] in removed_schools:
                roles.remove(role)
        if new_schools or removed_schools:
            self.roles_as_dicts = roles
