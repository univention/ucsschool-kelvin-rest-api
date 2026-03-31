.. list-table:: SchoolMembership — Columns (Part 1)
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
   * - ``is_primary``
     - ``BOOLEAN``
     -
     -
     -
     - ``False``
   * - ``primary_user_constraint``
     - ``INTEGER``
     -
     - ✓
     - ✓
     -
   * - ``user_id``
     - ``INTEGER``
     -
     -
     - ``(user_id, school_id)``
     -
   * - ``school_id``
     - ``INTEGER``
     -
     -
     - ``(user_id, school_id)``
     -

.. list-table:: SchoolMembership — Columns (Part 2)
   :header-rows: 1
   :widths: 14 28 14

   * - Name
     - Description
     - UDM
   * - ``primary_user_constraint``
     - This is an internally managed field only, to ensure at most one primary school per user.
     - ````
