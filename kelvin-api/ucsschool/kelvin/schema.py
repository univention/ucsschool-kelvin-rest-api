# SPDX-FileCopyrightText: 2026 Univention GmbH
# SPDX-License-Identifier: AGPL-3.0-only

"""OpenAPI schema helpers for the Kelvin API models."""

from typing import cast

from pydantic import BaseModel

JsonSchema = dict[str, object]


def mark_nullable_properties(schema: JsonSchema, model: type[BaseModel]) -> None:
    """
    Add ``nullable: true`` to every property of `schema` whose field accepts ``None``.

    pydantic 1.x knows which fields accept ``None`` (``ModelField.allow_none``) but does
    not put that information into the generated JSON schema. Without this, a response
    containing ``"birthday": null`` contradicts a schema that declares ``birthday`` to be
    a date string.

    Fields listed in the model's ``Config.non_nullable_fields`` are skipped. Use it for
    fields that pydantic considers nullable only because they default to ``None``, while
    a validator rejects an explicitly passed ``None``.
    """
    properties = cast(JsonSchema, schema.get("properties", {}))
    non_nullable: tuple[str, ...] = getattr(model.__config__, "non_nullable_fields", ())
    for field in model.__fields__.values():
        if not field.allow_none or field.name in non_nullable:
            continue
        prop = cast("JsonSchema | None", properties.get(field.alias))
        if prop is None:
            continue
        if "$ref" in prop:
            # OpenAPI 3.0 ignores any keyword next to '$ref', so the reference has to
            # be wrapped before 'nullable' can be attached to it.
            prop["allOf"] = [{"$ref": prop.pop("$ref")}]
        prop["nullable"] = True


class KelvinBaseModel(BaseModel):
    """Base class of all models that appear in the Kelvin API's OpenAPI document."""

    class Config:
        non_nullable_fields: tuple[str, ...] = ()

        @staticmethod
        def schema_extra(schema: JsonSchema, model: type[BaseModel]) -> None:
            mark_nullable_properties(schema, model)
