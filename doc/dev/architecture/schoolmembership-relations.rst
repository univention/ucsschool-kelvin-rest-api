.. list-table:: SchoolMembership — Relationships
   :header-rows: 1
   :widths: 20 20 15 10 20

   * - Attribute
     - Target
     - Direction
     - Collection
     - Back-ref
   * - ``user``
     - ``User``
     - Many → One
     -
     -
   * - ``school``
     - ``School``
     - Many → One
     -
     -
   * - ``groups``
     - ``Group``
     - Many ↔ Many
     - ✓
     - ``members``
   * - ``roles``
     - ``Role``
     - Many ↔ Many
     - ✓
     -
