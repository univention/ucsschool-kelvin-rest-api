# SPDX-FileCopyrightText: 2026 Univention GmbH
# SPDX-License-Identifier: AGPL-3.0-only

import inspect
import logging
from typing import Any, Dict

import lazy_object_proxy
from six import iteritems

from .attributes import Attribute


class UCSSchoolHelperOptions(object):
    def __init__(self, klass, meta=None):
        self.set_from_meta_object(meta, "udm_module", None)
        self.set_from_meta_object(meta, "udm_filter", "")
        self.set_from_meta_object(meta, "name_is_unique", False)
        self.set_from_meta_object(meta, "allow_school_change", False)
        # Manually set cls.meta.ldap_name_part, because we cannot ask UDM, 'cn' is the default,
        # overwrite it in classes that use something else, like User (uid) and School (ou). Used in
        # UCSSchoolHelperAbstractClass.dn() to calculate the DN of school objects:
        self.set_from_meta_object(meta, "ldap_name_part", "cn")
        self.set_from_meta_object(meta, "ignore_meta", False)
        udm_module_short = None
        if self.udm_module:
            udm_module_short = self.udm_module.split("/")[1]
        self.set_from_meta_object(meta, "udm_module_short", udm_module_short)
        self.set_from_meta_object(meta, "_ldap_filter", "")

    def set_from_meta_object(self, meta, name, default):
        setattr(self, name, getattr(meta, name, default))


class UCSSchoolHelperMetaClass(type):
    def __new__(mcs, cls_name, bases, attrs):
        attributes = {}
        meta = None

        def scan_class_attributes(class_attrs: Dict[str, Any]) -> None:
            # side effect: changes "attributes" dict from function scope
            for name, value in iteritems(class_attrs):
                if name in attributes:
                    # allows to remove an attribute from a subclass
                    # hierarchie should better have been architectured differently (e.g. using mixins)
                    del attributes[name]
                if type(value) is lazy_object_proxy.Proxy:
                    # The isinstance() below will access the value and create an InitialisationError in
                    # ImportUser.config and ImportUser.factory, as they are not initialized at import
                    # time. Interestingly type() does not do that.
                    continue
                if isinstance(value, Attribute):
                    attributes[name] = value

        # collect attributes and "Meta" (_meta) from all base classes in the
        # order from most basic to most special
        for base in reversed(bases):
            if hasattr(base, "_meta") and not getattr(base._meta, "ignore_meta", False):
                meta = base._meta
            # works for classes inheriting from UCSSchoolHelperAbstractClass:
            if hasattr(base, "_attributes"):
                attributes.update(base._attributes)
            # works also for mixins:
            scan_class_attributes(vars(base))

        # attributes and "Meta" of top class (the one currently being created)
        # is read last, as it's the "most special"
        meta = attrs.get("Meta") or meta
        scan_class_attributes(attrs)

        cls = super(UCSSchoolHelperMetaClass, mcs).__new__(mcs, cls_name, bases, dict(attrs))
        cls._attributes = attributes
        cls._meta = UCSSchoolHelperOptions(cls, meta)
        cls.logger: logging.Logger = lazy_object_proxy.Proxy(
            lambda: logging.getLogger(inspect.getmodule(cls).__name__)
        )
        return cls
