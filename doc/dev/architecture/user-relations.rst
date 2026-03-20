.. list-table:: User — Relationships
   :header-rows: 1
   :widths: 20 20 15 10 20

   * - Attribute
     - Target
     - Direction
     - Collection
     - Back-ref
   * - ``legal_wards``
     - ``User``
     - Many ↔ Many
     - ✓
     - ``legal_guardians``
   * - ``legal_guardians``
     - ``User``
     - Many ↔ Many
     - ✓
     - ``legal_wards``
   * - ``school_memberships``
     - ``SchoolMembership``
     - One → Many
     - ✓
     - ``user``
