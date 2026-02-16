.. SPDX-FileCopyrightText: 2026 Univention GmbH
..
.. SPDX-License-Identifier: AGPL-3.0-only

Synchronization to Nubus
========================

* 🚧 Why is there a Kelvin connector?
* 🚧 ...

Sync architecture
-----------------

* 🚧 How is the sync service structured?
* 🚧 Which interfaces of Nubus are used? (UDM REST, Provisioning service?)
* 🚧 How is reliability ensured (retry, dead letter queue)?

Events
------

* 🚧 What events are there (e.g., ``user created``, ``group changed``)?
* 🚧 How is the event schema structured? Who produces, who consumes?

Conflict handling
-----------------

* 🚧 What happens when simultaneous changes are made in both directions?
* 🚧 What conflict resolution strategy applies (last write wins, merge, manual)?
* 🚧 How are conflicts logged? How are customers notified?

