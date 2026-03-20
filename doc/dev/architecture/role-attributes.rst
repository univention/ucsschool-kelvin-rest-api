.. list-table:: Role — Columns
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
