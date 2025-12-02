What to do in case of errors
============================

When you encounter an error while using the Kelvin REST API, this can be for different reasons:

* A service that the Kelvin API is depending on is unavailable or encounters itself an error when responding to a request from the Kelvin API.
* A UCS\@school object has been changed by another service/party without complying to the UCS\@school rules.
* Kelvin is not configured correctly.
* A bug in Kelvin or a service Kelvin depends on.
* Network or other infrastructure problems.

Depending on your role when working with Kelvin and encountering an error,
you have different sources of information.

.. _errors-as-a-user:

Dealing with errors as a user
-----------------------------

As a user of the API, you will receive the HTTP status code
and error message returned from the API as an indicator what happened with your request.

.. code-block:: json

   {
      "detail": [
           {
              "loc": [],
              "msg": "UDM REST Unavailable",
              "type": "UdmError:APICommunicationError"
           }
       ]
   }

.. code-block:: json


   {
     "detail": [
       {
         "loc": [
           "body",
           "firstname"
         ],
         "msg": "field required",
         "type": "value_error.missing"
       }
     ]
   }


When an error occurs after the validation phase and not related to UDM, the error response content has a different format:

.. code-block:: json

   {
      "detail": "{'school_classes': [\"School 'DEMOSCHOOL' in 'school_classes' is missing in the users 'school(s)' attributes.\"]}"
   }

When the error is not on the user side, like in the first example,
the next step is to involve the operator or administrator of the Kelvin API
and forward the request and response data to him.

.. _errors-as-an-administrator:

Dealing with errors as an administrator
---------------------------------------

As an administrator with credentials for the host of the Kelvin API, you have access to the log files.
The log file ``/var/log/univention/ucsschool-kelvin-rest-api/http.log`` contains log messages of the Kelvin API.
Alternatively, use the command ``univention-app logs ucsschool-kelvin-rest-api``.
Depending on the problem, other log files may be helpful as well. For example, the UDM REST API, on which the
Kelvin API depends, is relevant when you receive an ``UdmError:APICommunicationError`` which is shown in :ref:`the last section <errors-as-a-user>`.
Relevant logs for the UDM REST API can be found in :file:`/var/log/univention/directory-manager-rest.log`.

If the problem persists or is reproducible, it is helpful to increase the log level to :code:`DEBUG`
to increase the amount of information:

.. code:: sh

   univention-app configure ucsschool-kelvin-rest-api --set ucsschool/kelvin/log_level=DEBUG
   univention-app restart ucsschool-kelvin-rest-api

To increase the log information for the UDM REST API raise the level that is set for the UCR variable ``directory/manager/rest/debug/level``.


Kelvin's log statements look like the following:

.. code::

   2025-12-17 15:10:53 INFO  [198][5b4b080a5e] h11_impl.send:473  172.17.42.1:50274 - "PATCH /ucsschool/kelvin/v1/users/demo_student HTTP/1.1" 200

The typical log statement parts for Kelvin are:

1. Date- and Timestamp ``2025-12-08 12:59:13``
2. Log level ``INFO``
3. Process ID ``[198]``
4. Correlation ID ``[5b4b080a5e]``
5. The actual message or event

In this case, the log message tells us that a patch request with path ``/ucsschool/kelvin/v1/users/demo_student`` succeeded with status code 200.

.. code::

   2025-12-17T15:10:53.670104+01:00     INFO [5b4b080a5e] 200 GET /udm/users/user/uid=demo_student,cn=schueler,cn=users,ou=school1,dc=school,dc=test (0.0.0.0) 8.51ms	| pid=367412 logname=tornado.access func=web.log_request:2279 requester_dn="cn=admin,dc=school,dc=test" requester_ip=172.17.0.1


The typical log statement parts for UDM are:

1. Date- and Timestamp ``2025-12-17T15:10:53.670104+01:00``
2. Log level ``INFO``
3. Correlation ID ``[5b4b080a5e]``
4. The actual message or event

In this case, the log message states that a GET request with path
:code:`/udm/users/user/uid=demo_student,cn=schueler,cn=users,ou=school1,dc=school,dc=test`
succeeded with status code :code:`200`.

The two log messages are related: They have the same correlation ID ``[5b4b080a5e]``.
When an HTTP request to Kelvin contains a header with the name ``X-Request-ID`` its value will be used for the correlation ID, otherwise Kelvin will generate an ID.
All log messages which are done in the context of this request will contain that correlation ID.
When Kelvin requests information from UDM, this correlation ID will be passed along, and hence log messages of UDM can be correlated with Kelvin log messages.


Example Bug
^^^^^^^^^^^

To give an example for how an Administrator could gather all available information,
lets introduce a severe bug into the UDM service which occurs on each user modification.


A partial update to a user (:code:`PATCH` against path :code:`/ucsschool/kelvin/v1/users/demo_student`) with the following payload:

.. code-block:: json

   {"lastname": "student"}

Leads to an internal server error with status code 500:

.. code-block:: json

   {
      "detail": [
         {
            "loc": [],
            "msg": "Internal Server Error",
            "type": "UdmError:APICommunicationError"
         }
      ]
   }


if you have the correlation ID, e.g. from the ``X-Request-ID`` you can search for it in the logs.
If you don't have the correlation ID,
try to make a guess by checking the Kelvin log for a correlation ID that matches the time and argument of your request.

.. code-block:: bash

   grep .*89bbd1f5fe /var/log/univention/ucsschool-kelvin-rest-api/http.log

You can see that the error happens during an update of the :code:`demo_student` user within the UDM service.

.. code-block::

   2025-12-18 14:50:12 ERROR [199][89bbd1f5fe] main.udm_exception_handler:166  Encountered exception [HTTP 500]: for operation 'update' on 'users/user' with arguments {'users_user': {'options': {'pki': False, 'ucsschoolStudent': True, 'ucsschoolTeacher': False, 'ucsschoolStaff': False, 'ucsschoolAdministrator': False, 'ucsschoolExam': False, 'ucsschoolLegalGuardian': False}, 'position': 'cn=schueler,cn=users,ou=DEMOSCHOOL,dc=school,dc=test', 'properties': {'lastname': 'student', 'overridePWHistory': False, 'overridePWLength': False}}, 'dn': 'uid=demo_student,cn=schueler,cn=users,ou=DEMOSCHOOL,dc=school,dc=test'}: Internal Server Error responding with [{'loc': (), 'msg': 'Internal Server Error', 'type': 'UdmError:APICommunicationError'}]
   2025-12-18 14:50:12 INFO  [199][89bbd1f5fe] h11_impl.send:473  172.17.42.1:45752 - "PATCH /ucsschool/kelvin/v1/users/demo_student HTTP/1.1" 500

The first line shows information about the request that was sent to UDM, which is also helpful for debugging.

Proceeding to the UDM REST service logs:

.. code-block:: bash

   grep .*89bbd1f5fe /var/log/univention/directory-manager-rest.log

You can now see that there is an uncaught exception:

.. code-block::

   2025-12-18T14:50:12.886964+01:00    ERROR [89bbd1f5fe] "Uncaught exception PATCH /udm/users/user/uid=demo_student,cn=schueler,cn=users,ou=DEMOSCHOOL,dc=school,dc=test (0.0.0.0) ...
   2025-12-18T14:50:12.889553+01:00    ERROR [89bbd1f5fe] 500 PATCH /udm/users/user/uid=demo_student,cn=schueler,cn=users,ou=DEMOSCHOOL,dc=school,dc=test (0.0.0.0) 25.44ms	| pid=555410 logname=tornado.access func=web.log_request:2279 requester_dn="cn=admin,dc=school,dc=test" requester_ip=172.17.0.1


Opening the :file:`/var/log/univention/directory-manager-rest.log` will contain the full Python traceback,
which, at the end, includes the error message and source file path.

.. code-block::

   [...]
     File "/usr/lib/python3/dist-packages/univention/admin/handlers/users/user.py", line 1253, in modify
       raise Exception("BUG!")
   Exception: BUG!

In case of an error indicated by a traceback in the Kelvin or UDM REST logs,
you can help us by opening a bug against the Kelvin component in `Bugzilla <https://forge.univention.org/bugzilla/enter_bug.cgi?product=UCS%40school&component=HTTP-API%20%28Kelvin%29>`_.
To ensure that the developers have all the necessary information to work on the bug,
please attach log files and if possible describe how the error can be reproduced and how it impacts you.
