.. SPDX-FileCopyrightText: 2026 Univention GmbH
.. SPDX-License-Identifier: AGPL-3.0-only

.. list-table:: User — Columns (Part 1)
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
   * - ``firstname``
     - ``VARCHAR(255)``
     -
     -
     -
     -
   * - ``lastname``
     - ``VARCHAR(255)``
     -
     -
     -
     -
   * - ``email``
     - ``VARCHAR(255)``
     -
     - ✓
     - ✓
     -
   * - ``birthday``
     - ``DATE``
     -
     - ✓
     -
     -
   * - ``expiration_date``
     - ``DATE``
     -
     - ✓
     -
     -
   * - ``active``
     - ``BOOLEAN``
     -
     -
     -
     - ``True``

.. list-table:: User — Columns (Part 2)
   :header-rows: 1
   :widths: 14 28 14

   * - Name
     - Description
     - UDM
   * - ``public_id``
     -
     - ``univentionObjectIdentifier``
   * - ``record_uid``
     - The ``record_uid`` is the ID for record of this user of an external source which is itself identified by the source_uid
     - ``ucsschoolRecordUID``
   * - ``source_uid``
     - The ``source_uid`` is the ID of the source of this user, which could be an external database.
     - ``ucsschoolSourceUID``
   * - ``name``
     -
     - ``username``
   * - ``firstname``
     -
     - ``firstname``
   * - ``lastname``
     -
     - ``lastname``
   * - ``email``
     -
     - ``mailPrimaryAddress``
   * - ``birthday``
     -
     - ``birthday``
   * - ``expiration_date``
     -
     - ``userexpiry``
   * - ``active``
     -
     - ``disabled``
