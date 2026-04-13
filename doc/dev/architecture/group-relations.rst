.. SPDX-FileCopyrightText: 2026 Univention GmbH
.. SPDX-License-Identifier: AGPL-3.0-only

.. list-table:: Group — Relationships
   :header-rows: 1
   :widths: 20 20 15 10 20

   * - Attribute
     - Target
     - Direction
     - Collection
     - Back-ref
   * - ``group_type``
     - ``GroupType``
     - Many → One
     -
     -
   * - ``school``
     - ``School``
     - Many → One
     -
     -
   * - ``members``
     - ``SchoolMembership``
     - Many ↔ Many
     - ✓
     - ``groups``
   * - ``allowed_email_senders_users``
     - ``User``
     - Many ↔ Many
     - ✓
     -
   * - ``allowed_email_senders_groups``
     - ``Group``
     - Many ↔ Many
     - ✓
     -
   * - ``member_roles``
     - ``Role``
     - Many ↔ Many
     - ✓
     -
