.. list-table:: School — Columns (Part 1)
   :header-rows: 1
   :widths: 14 12 5 5 10 15

   * - Name
     - Type
     - PK
     - Nullable
     - Unique
     - Default
   * - ``id``
     - ``INTEGER``
     - ✓
     -
     -
     -
   * - ``public_id``
     - ``UUID``
     -
     -
     - ✓
     - ``uuid4()``
   * - ``record_uid``
     - ``VARCHAR(255)``
     -
     -
     - ``(record_uid, source_uid)``
     -
   * - ``source_uid``
     - ``VARCHAR(255)``
     -
     -
     - ``(record_uid, source_uid)``
     -
   * - ``name``
     - ``VARCHAR(255)``
     -
     -
     - ✓
     -
   * - ``display_name``
     - ``JSON``
     -
     -
     -
     - ``dict()``
   * - ``educational_servers``
     - ``JSON``
     -
     -
     -
     - ``list()``
   * - ``administrative_servers``
     - ``JSON``
     -
     -
     -
     - ``list()``
   * - ``class_share_file_server``
     - ``VARCHAR(255)``
     -
     - ✓
     -
     -
   * - ``home_share_file_server``
     - ``VARCHAR(255)``
     -
     - ✓
     -
     -

.. list-table:: School — Columns (Part 2)
   :header-rows: 1
   :widths: 14 28 14

   * - Name
     - Description
     - UDM
   * - ``public_id``
     -
     - ``univentionObjectIdentifier``
   * - ``record_uid``
     - The ``record_uid`` is the ID for record of this school of an external source, which is itself identified by the source_uid
     - ``ucsschoolRecordUID``
   * - ``source_uid``
     - The ``source_uid`` is the ID of the source of this school, which could be an external database.
     - ``ucsschoolSourceUID``
   * - ``display_name``
     -
     - ``displayName``
