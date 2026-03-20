.. list-table:: SchoolMembership — Columns
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
