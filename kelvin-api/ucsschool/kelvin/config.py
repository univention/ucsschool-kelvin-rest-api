# SPDX-FileCopyrightText: 2026 Univention GmbH
# SPDX-License-Identifier: AGPL-3.0-only

from typing import Any, Dict, List

import lazy_object_proxy
from pydantic.fields import FieldInfo
from pydantic_settings import (
    BaseSettings,
    JsonConfigSettingsSource,
    PydanticBaseSettingsSource,
    SettingsConfigDict,
)
from typing_extensions import override

from ..importer.configuration import ReadOnlyDict
from ..importer.models.import_user import ImportUser
from ..lib.models.group import SchoolClass, WorkGroup
from ..lib.models.school import School
from .constants import UDM_MAPPED_PROPERTIES_CONFIG_FILE
from .exceptions import InvalidConfiguration
from .import_config import get_import_config


def import_config_udm_mapping_source() -> Dict[str, Any]:
    config: ReadOnlyDict = get_import_config()
    if "mapped_udm_properties" in config:
        return {"user": config.get("mapped_udm_properties")}
    else:
        return {}


class ImportConfigUDMMappingSource(PydanticBaseSettingsSource):
    """The `mapped_udm_properties` of the import configuration, as the users' UDM properties."""

    @override
    def get_field_value(self, field: FieldInfo, field_name: str) -> tuple[Any, str, bool]:
        return None, field_name, False  # pragma: no cover

    @override
    def __call__(self) -> Dict[str, Any]:
        return import_config_udm_mapping_source()


class UDMMappingConfiguration(BaseSettings):
    school: List[str] = []
    user: List[str] = []
    school_class: List[str] = []
    workgroup: List[str] = []

    model_config = SettingsConfigDict(
        json_file=UDM_MAPPED_PROPERTIES_CONFIG_FILE, json_file_encoding="utf-8"
    )

    @classmethod
    @override
    def settings_customise_sources(
        cls,
        settings_cls: type[BaseSettings],
        init_settings: PydanticBaseSettingsSource,
        env_settings: PydanticBaseSettingsSource,
        dotenv_settings: PydanticBaseSettingsSource,
        file_secret_settings: PydanticBaseSettingsSource,
    ) -> tuple[PydanticBaseSettingsSource, ...]:
        return (
            init_settings,
            JsonConfigSettingsSource(settings_cls),
            ImportConfigUDMMappingSource(settings_cls),
        )

    def prevent_mapped_attributes_in_udm_properties(self):
        """
        Make sure users do not configure values for ucsschool.lib mapped Attributes
        in udm_properties.
        """
        for udm_properties, lib_model in [
            (self.school, School),
            (self.user, ImportUser),
            (self.school_class, SchoolClass),
            (self.workgroup, WorkGroup),
        ]:
            bad_props = set(udm_properties).intersection(lib_model.attribute_udm_names())
            if bad_props:
                raise InvalidConfiguration(
                    "UDM properties '{}' must be set as attributes of the {} object (not in "
                    "udm_properties).".format("', '".join(bad_props), lib_model.__name__)
                )


UDM_MAPPING_CONFIG: UDMMappingConfiguration = lazy_object_proxy.Proxy(UDMMappingConfiguration)


def load_configurations():
    """
    This function can be called to initialize all settings in this module
    in case an early abort for faulty configuration is desired.
    """
    UDM_MAPPING_CONFIG.prevent_mapped_attributes_in_udm_properties()
