# Task 008 — kelvin-api startup validation for indexed UDM properties

**Status:** not started

## Objective

Add a fail-fast startup check in `kelvin-api` ensuring that any UDM property
configured for indexing (Task 006's config) is actually a subset of that
entity's mapped UDM properties (`UDM_MAPPING_CONFIG`) — mirroring the
existing `prevent_mapped_attributes_in_udm_properties()` pattern.

## Context

See [`../context.md`](../context.md), especially Risk 2 (ordering hazard):
this check validates config *consistency*, not that the corresponding
migration (Task 007) has actually been run — that distinction must be
documented inline, not just implied.

Existing pattern to mirror, `kelvin-api/ucsschool/kelvin/config.py`
(lines 70-97):
```python
class UDMMappingConfiguration(BaseSettings):
    school: List[str] = []
    user: List[str] = []
    school_class: List[str] = []
    workgroup: List[str] = []
    ...
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
                raise InvalidConfiguration(...)

UDM_MAPPING_CONFIG: UDMMappingConfiguration = lazy_object_proxy.Proxy(UDMMappingConfiguration)

def load_configurations():
    """
    This function can be called to initialize all settings in this module
    in case an early abort for faulty configuration is desired.
    """
    UDM_MAPPING_CONFIG.prevent_mapped_attributes_in_udm_properties()
```

`load_configurations()` is invoked at startup from
`kelvin-api/ucsschool/kelvin/service/lifespan.py`.

## Scope

- `kelvin-api/ucsschool/kelvin/config.py` only.
- New function `prevent_unmapped_indexed_udm_properties()` (module-level or a
  method, matching whatever's more consistent with the existing function's
  placement).
- Wire it into `load_configurations()` alongside the existing call.

## Non-goals

- Checking whether the corresponding index actually exists in the database
  (would require a DB round-trip at every startup — explicitly rejected as
  over-engineering, see Risk 2 in `../context.md`). This task only validates
  config-to-config consistency.
- Any change to `UDMMappingConfiguration` itself.

## Dependencies

Task 006 (imports `build_indexed_udm_properties_config` from it).

## Implementation steps

1. Add the import:
   ```python
   from ucsschool_objects.core.adapters.sqlalchemy.indexed_udm_properties import (
       build_indexed_udm_properties_config,
   )
   ```
2. Add the validation function:
   ```python
   def prevent_unmapped_indexed_udm_properties():
       """
       Make sure every UDM property configured for indexing (see
       ucsschool_objects.core.adapters.sqlalchemy.indexed_udm_properties) is
       also configured as a mapped UDM property for that entity.

       Note: this only validates configuration consistency. It does NOT
       verify that the corresponding database index has actually been
       created (that requires running the Alembic migration in
       alembic/versions/<...>_add_configurable_udm_property_indexes.py) —
       see docs/plan/context.md Risk 2 for the accepted operational gap
       this leaves.
       """
       indexed = build_indexed_udm_properties_config()
       for entity, indexed_props, mapped_props in (
           ("user", indexed.user, UDM_MAPPING_CONFIG.user),
           ("school", indexed.school, UDM_MAPPING_CONFIG.school),
           ("school_class", indexed.school_class, UDM_MAPPING_CONFIG.school_class),
           ("workgroup", indexed.workgroup, UDM_MAPPING_CONFIG.workgroup),
       ):
           unmapped = set(indexed_props) - set(mapped_props)
           if unmapped:
               raise InvalidConfiguration(
                   "UDM properties {} are configured for indexing on {!r} but "
                   "are not in the corresponding UDM_MAPPING_CONFIG list.".format(
                       "', '".join(sorted(unmapped)), entity
                   )
               )
   ```
3. Wire into `load_configurations()`:
   ```python
   def load_configurations():
       UDM_MAPPING_CONFIG.prevent_mapped_attributes_in_udm_properties()
       prevent_unmapped_indexed_udm_properties()
   ```

## Acceptance criteria

- Startup succeeds when indexed-UDM-properties config is empty or a subset
  of `UDM_MAPPING_CONFIG`.
- Startup raises `InvalidConfiguration` with a clear message listing the
  offending properties when an indexed property isn't mapped.
- The "does not verify the index/migration has run" limitation is documented
  in the function's docstring, not just in planning docs.

## Validation / test steps

- New unit test(s) alongside existing config tests (check
  `kelvin-api/tests/` for where `UDMMappingConfiguration`/
  `prevent_mapped_attributes_in_udm_properties` are already tested, and add
  siblings there) covering: empty config passes; subset passes; superset
  (indexed property not in mapped list) raises with the right message.
- Run via kelvin-api's test command (see `kelvin-api/Makefile`).

## Likely files to inspect or modify

- `kelvin-api/ucsschool/kelvin/config.py` (modify)
- `kelvin-api/ucsschool/kelvin/service/lifespan.py` (read only — confirms
  `load_configurations()` call site, likely no changes needed there)
- Existing test file covering `config.py` (find and extend — search for
  `prevent_mapped_attributes_in_udm_properties` in `kelvin-api/tests/`)

## Open questions / blockers

Blocked on Task 006 existing.

## Notes for next session

- If Task 006's env var names or module path change, update the import here.
