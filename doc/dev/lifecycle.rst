.. SPDX-FileCopyrightText: 2026 Univention GmbH
..
.. SPDX-License-Identifier: AGPL-3.0-only

Application Lifecycle
=====================


Kelvin Database
---------------

When a new Kelvin Application is installed on a backup or primary node, the app settings
will prompt the App center to automatically create a database named
``ucsschool-kelvin-rest-api`` on that node.

The ``configure_host`` App center script manages a ``settings/data`` object which is
used by subsequent installations on nodes in the same domain to connect to the same database.
The first installation determines the the active database unless the App settings are explicitly
changed to use a different database.

.. code-block:: bash
   :caption: Snippet to extract the contents of the ``settings/data`` object

   data=$(udm settings/data list --filter cn=ucsschool-kelvin-rest-api --properties data | grep -oP '(?<= data: ).*') && echo $data | base64 -d | bzcat


.. code-block:: bash
   :caption: Manual modification for testing

   udm settings/data modify --dn 'cn=ucsschool-kelvin-rest-api,cn=data,cn=univention,dc=ucsschool,dc=test' --set data="$(bzip2 < test.json | base64)

.. code-block:: json
   :caption: Example contents of an ``ucsschool-kelvin-rest-api`` ``settings/data`` object

   {
     "database-uri": "postgresql://backup1.school.test:5432/kelvin?sslmode=require",
     "database-user": "kelvin",
     "database-password-host": "primary.ucsschool.test",
     "database-password-path": "/etc/ucsschool/kelvin/postgresql-kelvin.secret",
     "installations": [
       "primary.ucsschool.test",
       "backup1.ucsschool.test",
       "backup2.ucsschool.test"
     ]
   }


.. mermaid::
   :caption: In this example, the first installation on Node 2 determined the active database.

   graph TB
       subgraph Node1["Node 1 (Primary)"]
           App1[("Kelvin Instance")]
           DB1[(Kelvin DB<br/>UNUSED)]
       end

       subgraph Node2["Node 2 (Backup)"]
           App2[("Kelvin Instance")]
           DB2[(Kelvin DB<br/>ACTIVE)]
       end

       subgraph Node3["Node 3 (Backup)"]
           App3[("Kelvin Instance")]
           DB3[(Kelvin DB<br/>UNUSED)]
       end

       App1 -.->|connects to| DB2
       App2 -.->|connects to| DB2
       App3 -.->|connects to| DB2


When an application is removed from a node, the ``uinst`` App center script will
delete the installation from the ``settings/data`` object``. If the last installation is removed,
the ``settings/data`` object will be deleted.

Note that the app settings are saved for the Application by the App center, so when the app is reinstalled,
the current node may not be the one that hosts the active database by default.
