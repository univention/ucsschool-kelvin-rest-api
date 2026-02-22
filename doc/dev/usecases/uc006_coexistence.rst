.. _uc006_coexistence:

.. preview-start

:ref:`UC-006: Coexistence with Kelvin V1<uc006_coexistence>`
------------------------------------------------------------

:Actor: All actors, Kelvin V1
:Priority: Must-have

During the migration phase both Kelvin V1 and Kelvin V2 run simultaneously.
Kelvin V1 persists data synchronously in LDAP (via UDM REST API).
Kelvin V2 persists data in the School database (PostgreSQL).
An asynchronous synchronization process (UDM-to-School) propagates changes
made through Kelvin V1 into the School database so that Kelvin V2 can read them.

When an object is created, updated, or deleted through Kelvin V1,
the change lands directly in LDAP. The LDAP change triggers
the UDM-to-School process (a Nubus Provisioning Consumer), which transforms
the UDM object into a School object and writes it to the School database.
Kelvin V2 can then read the updated data.

This allows actors to continue using Kelvin V1 for writes while already
benefiting from Kelvin V2's performance improvements for reads.

.. preview-end

Preconditions
^^^^^^^^^^^^^
- Kelvin V1 is deployed and operational (reads/writes via UDM REST API to LDAP)
- Kelvin V2 is deployed and operational (reads from School database)
- UDM-to-School synchronization process is running
- Actor is authenticated against the API version they are using

Main Flow
^^^^^^^^^
1. Actor creates, updates, or deletes an object through Kelvin V1
2. Kelvin V1 persists the change in LDAP via UDM REST API
3. LDAP change triggers the UDM-to-School process (Nubus Provisioning Consumer)
4. UDM-to-School process transforms the UDM object into a School object and writes it to the School database
5. Another actor (or the same actor) reads the object through Kelvin V2 and sees the updated data

Alternative Flows
^^^^^^^^^^^^^^^^^

**5a. Synchronization temporarily delayed:**
   1. Synchronization queue has a backlog due to high load
   2. Object is not yet visible (or still shows old state) through Kelvin V2
   3. Eventually (once the queue is processed) the object becomes visible

Exception Flows
^^^^^^^^^^^^^^^

**3a. UDM-to-School process is unavailable:**
   1. Events remain in the provisioning queue
   2. Changes made through Kelvin V1 are not visible through Kelvin V2 until the process recovers
   3. Once the process recovers, queued events are processed in order

**4a. Change violates a constraint in the School database:**
   1. The UDM-to-School process attempts to apply the change
   2. The School database rejects it (e.g. constraint violation)
   3. The rejection is logged and accessible to administrators
   4. The object remains in its previous state in the School database

Postconditions
^^^^^^^^^^^^^^
- Object in the School database is eventually consistent with LDAP
- Synchronization failures are logged and accessible to administrators
- Audit log entries created in both API versions

Sequence Diagram
^^^^^^^^^^^^^^^^

.. mermaid::

   sequenceDiagram
       participant ActorA as Actor (V1 client)
       participant V1 as Kelvin V1 API
       participant UDM as UDM REST API
       participant LDAP as LDAP
       participant U2S as UDM-to-School Process
       participant SchoolDB as PostgreSQL (School DB)
       participant V2 as Kelvin V2 API
       participant ActorB as Actor (V2 client)

       ActorA ->> V1: POST/PATCH/DELETE /<object>
       V1 ->> UDM: Create/update/delete UDM object
       UDM ->> LDAP: Persist in LDAP
       V1 ->> ActorA: 200 OK / 201 Created

       LDAP ->> U2S: LDAP change triggers provisioning
       U2S ->> SchoolDB: Persist School object

       ActorB ->> V2: GET /<object>
       V2 ->> SchoolDB: Read object
       V2 ->> ActorB: 200 OK (updated data)
