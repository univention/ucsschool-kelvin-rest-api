# -*- coding: utf-8 -*-
#
# Univention UCS@school
# Copyright 2017-2021 Univention GmbH
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
Base class for all Python based import hooks.
"""

from __future__ import absolute_import

import logging
from typing import Any, Callable, Dict, List, Optional, Type, TypeVar, Union

from ucsschool.lib.pyhooks import PyHook, PyHooksLoader
from udm_rest_client import UDM
from univention.admin.uldap import LoType

from ..exceptions import InitialisationError
from .ldap_connection import get_admin_connection, get_readonly_connection

ImportPyHookTV = TypeVar("ImportPyHookTV", bound="ImportPyHook")

__import_pyhook_loader_instance: Optional["ImportPyHookLoader"] = None


class ImportPyHook(PyHook):
    """
    Base class for Python based import hooks.

    * self.dry_run     # always ``False`` in the context of the Kelvin API
    * self.lo          # LDAP connection object (1)
    * self.logger      # Python logging instance
    * self.udm         # UDM REST Client instance (2)

    If multiple hook classes are found, hook functions with higher
    priority numbers run before those with lower priorities. None disables
    a function (no need to remove it / comment it out).

    (1) Read-write cn=admin LDAP connection, attention: LDAP attributes
            returned by get() and search() are now ``bytes`´, not ``str``
    (2) Read-write cn=admin UDM REST API connection, see
            https://udm-rest-client.readthedocs.io/en/latest/
    """

    supports_dry_run = False  # if True hook will be executed during a dry-run

    def __init__(
        self,
        lo: LoType = None,
        dry_run: bool = None,
        udm: UDM = None,
        *args,
        **kwargs,
    ) -> None:
        """
        :param univention.admin.uldap.access lo: optional LDAP connection object
        :param bool dry_run: whether hook is executed during a dry-run
        :param UDM udm: UDM REST Client instance
        """
        super(ImportPyHook, self).__init__(*args, **kwargs)
        if dry_run is None:
            from ..configuration import Configuration

            try:
                config = Configuration()
                self.dry_run = config["dry_run"]
                """Whether this is a dry-run"""
            except InitialisationError:
                self.dry_run = False
        else:
            self.dry_run = dry_run
        if lo is None:
            self.lo: LoType = get_readonly_connection()[0] if self.dry_run else get_admin_connection()[0]
            """LDAP connection object"""
        else:
            self.lo = lo  # reuse LDAP object
            """LDAP connection object"""
        self.logger: logging.Logger = logging.getLogger(__name__)
        """Python logging instance"""
        self.udm = udm
        """udm_rest_client.UDM instance"""


class ImportPyHookLoader(object):
    """
    Load and initialize hooks.

    If hooks should be instantiated with arguments, use :py:meth:`init_hook()`
    before :py:meth:`call_hook()`.
    """

    _pyhook_obj_cache: Dict[Type[ImportPyHookTV], Dict[str, List[Callable[..., Any]]]] = {}

    def __init__(self, pyhooks_base_path: str) -> None:
        self.pyhooks_base_path = pyhooks_base_path
        self.logger: logging.Logger = logging.getLogger(__name__)

    def init_hook(
        self,
        hook_cls: Union[Type[ImportPyHookTV], str],
        filter_func: Callable[[Type[ImportPyHookTV]], bool] = None,
        *args,
        **kwargs,
    ) -> Dict[str, List[Callable[..., Any]]]:
        """
        Load and initialize hook class `hook_cls`.

        :param hook_cls: class object - load and run hooks that are a subclass of this
        :type hook_cls: ucsschool.importer.utils.import_pyhook.ImportPyHook or str
        :param filter_func: function to filter out undesired hook classes (takes a
            class and returns a bool), passed to PyHooksLoader
        :type filter_func: callable or None
        :param tuple args: arguments to pass to __init__ of hooks
        :param dict kwargs: arguments to pass to __init__ of hooks
        :return: mapping from method names to list of methods of initialized
            hook objects, sorted by method priority
        :rtype: dict[str, list[callable]]
        """
        # The PyHook objects themselves are already cached by PyHooksLoader, but we don't want to
        # initialize a PyHooksLoader each time we run a hook, so we'll keep a dict linking directly to
        # all PyHooksLoader caches.
        base_class = PyHooksLoader.hook_cls2importpyhook(hook_cls, "hook_cls")
        if not issubclass(base_class, ImportPyHook):
            raise TypeError("Argument 'hook_cls' must be a subclass of ImportPyHook.")

        if base_class not in self._pyhook_obj_cache:
            pyhooks_loader = PyHooksLoader(self.pyhooks_base_path, base_class, self.logger, filter_func)
            self._pyhook_obj_cache[base_class] = pyhooks_loader.get_hook_objects(*args, **kwargs)
        return self._pyhook_obj_cache[base_class]

    def call_hooks(self, hook_cls: Type[ImportPyHookTV], func_name: str, *args, **kwargs) -> List[Any]:
        """
        Run hooks with name `func_name` from class `hook_cls`.

        :param hook_cls: class object - load and run hooks that are a
            subclass of this
        :param str func_name: name of method to run in each hook
        :param args: arguments to pass to hook function
        :param kwargs: arguments to pass to hook function
        :return: list of when all executed hooks returned
        :rtype: list
        """
        hooks = self.init_hook(hook_cls)

        res = []
        for func in hooks.get(func_name, []):
            self.logger.info("Running %s %s hook %s ...", self.__class__.__name__, func_name, func)
            res.append(func(*args, **kwargs))
        return res


def get_import_pyhooks(
    hook_cls: Union[Type[ImportPyHookTV], str],
    filter_func: Callable[[Type[ImportPyHookTV]], bool] = None,
    *args,
    **kwargs,
) -> Dict[str, List[Callable[..., Any]]]:
    """
    Retrieve (and initialize subclasses of :py:class:`hook_cls`, if not yet
    done) pyhooks of type `hook_cls`. Results are cached.

    If no argument must be passed to the `hook_cls` :py:meth:`__init__()` or
    :py:class:`PyHooksLoader`, then it is not necessary to call this function,
    just use :py:func:`run_import_pyhooks` directly.

    Convenience function for easy usage of PyHooksLoader.

    :param hook_cls: class object or fully dotted Python path to a class
        definition - load and run hooks that are a subclass of this
    :type hook_cls: ucsschool.importer.utils.import_pyhook.ImportPyHook or str
    :param filter_func: function to filter out undesired hook classes (takes a
        class and returns a bool), passed to PyHooksLoader
    :type filter_func: callable or None
    :param args: arguments to pass to __init__ of hooks
    :param kwargs: arguments to pass to __init__ of hooks
    :return: mapping from method names to list of methods of initialized
        hook objects, sorted by method priority
    :rtype: dict[str, list[callable]]
    """
    global __import_pyhook_loader_instance
    if not __import_pyhook_loader_instance:
        from ..configuration import Configuration

        try:
            config = Configuration()
            path = config.get("hooks_dir_pyhook", "/usr/share/ucs-school-import/pyhooks")
            if "dry_run" not in kwargs:
                kwargs["dry_run"] = config["dry_run"]
        except InitialisationError:
            path = "/usr/share/ucs-school-import/pyhooks"

        __import_pyhook_loader_instance = ImportPyHookLoader(path)

    return __import_pyhook_loader_instance.init_hook(hook_cls, filter_func, *args, **kwargs)


def run_import_pyhooks(hook_cls: Type[ImportPyHookTV], func_name: str, *args, **kwargs) -> List[Any]:
    """
    Execute method `func_name` of subclasses of `hook_cls`, load and
    initialize if required.

    Convenience function for easy usage of PyHooksLoader.

    :param hook_cls: class object or fully dotted Python path to a class
        definition - load and run hooks that are a subclass of this
    :type hook_cls: ucsschool.importer.utils.import_pyhook.ImportPyHook or str
    :param str func_name: name of method to run in each hook
    :param args: arguments to pass to hook function `func_name`
    :param kwargs: arguments to pass to hook function `func_name`
    :return: list of when all executed hooks returned
    :rtype: list
    """
    get_import_pyhooks(hook_cls)
    return __import_pyhook_loader_instance.call_hooks(hook_cls, func_name, *args, **kwargs)
