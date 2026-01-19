What to do in case of errors?
=============================

When you encounter an error while using the Kelvin REST API,
the errors can result from the following different reasons:

* Kelvin API depends on a service that's unavailable
  or encounters an error when responding to a request from the Kelvin API.

* Another service or party changes a UCS\@school object without complying to the UCS\@school rules.

* Kelvin isn't configured correctly.

* A bug in Kelvin or a service Kelvin depends on.

* Network or other infrastructure problems.

Depending on your role when working with Kelvin and encountering an error,
you have different sources of information.

.. _errors-as-a-user:

Dealing with errors as a user
-----------------------------

As a user of the Kelvin API,
you receive the HTTP status code and an error message.
The error message from the API indicates what happened with your request.
See the examples in
:numref:`errors-as-a-user-example-1-listing`
and :numref:`errors-as-a-user-example-2-listing`.

.. code-block:: json
   :caption: Example: UDM service unavailable error
   :name: errors-as-a-user-example-1-listing

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
   :caption: Example: validation error with missing field
   :name: errors-as-a-user-example-2-listing

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


When an error occurs after the validation phase
and isn't related to UDM, the error response content has a different format,
as shown in
:numref:`errors-as-a-user-example-3-listing`.

If the error isn't on the user side,
like in the first example in
:numref:`errors-as-a-user-example-1-listing`,
contact the operator or administrator of the Kelvin API
and provide them with the request and response data.

.. code-block:: json
   :caption: Example: error response for business logic violations
   :name: errors-as-a-user-example-3-listing

   {
      "detail": "{'school_classes': [\"School 'DEMOSCHOOL' in 'school_classes' is missing in the users 'school(s)' attributes.\"]}"
   }

.. _errors-as-an-administrator:

Dealing with errors as an administrator
---------------------------------------

As an administrator with access to the Kelvin API host,
you can access the log files.
The log file :file:`/var/log/univention/ucsschool-kelvin-rest-api/http.log` contains log messages of the Kelvin API.
Alternatively, use the command :command:`univention-app logs ucsschool-kelvin-rest-api`.
Other log files may be relevant depending on the problem.

For example, the *UDM HTTP REST API* is relevant for ``UdmError:APICommunicationError`` errors,
as shown in :ref:`errors-as-a-user`.
You can find relevant logging information for the *UDM HTTP REST API* in :file:`/var/log/univention/directory-manager-rest.log`.

If a problem persists or is reproducible,
you can increase the amount of logging information.
To increase the log level to :code:`DEBUG`,
use the commands in :numref:`errors-as-an-administrator-log-level-figure`.

To increase the log information for the *UDM HTTP REST API*,
also raise the level configured in the UCR variable :envvar:`directory/manager/rest/debug/level`.

.. code-block:: console
   :caption: Increase amount of information by changing the log level
   :name: errors-as-an-administrator-log-level-figure

   univention-app configure ucsschool-kelvin-rest-api --set ucsschool/kelvin/log_level=DEBUG
   univention-app restart ucsschool-kelvin-rest-api

The typical log statement for Kelvin has the following parts:

:Date- and Timestamp: ``2025-12-08 12:59:13``
:Log level: ``INFO``
:Process ID: ``[198]``
:Correlation ID: ``[5b4b080a5e]``
:Message: The actual message or event

Kelvin's log statements look like
:numref:`errors-as-an-administrator-example-log-kelvin-listing`.
The example shows a patch request to ``/ucsschool/kelvin/v1/users/demo_student``
that succeeded with HTTP status code ``200``.

.. code-block::
   :caption: Example for Kelvin log statement
   :name: errors-as-an-administrator-example-log-kelvin-listing

   2025-12-17 15:10:53 INFO  [198][5b4b080a5e] h11_impl.send:473  172.17.42.1:50274 - "PATCH /ucsschool/kelvin/v1/users/demo_student HTTP/1.1" 200

The typical log statement for UDM has the following parts:

:Date- and Timestamp: ``2025-12-17T15:10:53.670104+01:00``
:Log level: ``INFO``
:Correlation ID: ``[5b4b080a5e]``
:Message: The actual message or event

UDM log statements look like
:numref:`errors-as-an-administrator-example-log-udm-listing`.
The example shows a GET request to
``/udm/users/user/uid=demo_student,cn=schueler,cn=users,ou=school1,dc=school,dc=test``
that succeeded with HTTP status code ``200``.

.. code-block::
   :caption: Example for UDM log statement
   :name: errors-as-an-administrator-example-log-udm-listing

   2025-12-17T15:10:53.670104+01:00     INFO [5b4b080a5e] 200 GET /udm/users/user/uid=demo_student,cn=schueler,cn=users,ou=school1,dc=school,dc=test (0.0.0.0) 8.51ms	| pid=367412 logname=tornado.access func=web.log_request:2279 requester_dn="cn=admin,dc=school,dc=test" requester_ip=172.17.0.1

The log messages in
:numref:`errors-as-an-administrator-example-log-kelvin-listing`
and :numref:`errors-as-an-administrator-example-log-udm-listing`
relate to each other
through the same correlation ID ``[5b4b080a5e]``.
If an HTTP request to Kelvin contains a header with the name ``X-Request-ID``,
Kelvin uses its value for the correlation ID,
otherwise Kelvin generates one.
All log messages in the context of this request contain that correlation ID.
When Kelvin requests information from UDM,
it passes the correlation ID along
allowing you to correlate the logs.

.. _errors-example-bug:

Example Bug
-----------

To demonstrate how an administrator gathers information,
let's introduce a severe bug in the UDM service
that occurs on each user modification.

:numref:`errors-example-bug-payload-listing`
shows a partial update to a user with the payload.
The request is a ``PATCH`` against path ``/ucsschool/kelvin/v1/users/demo_student``.

.. code-block:: json
   :caption: Payload for user object update
   :name: errors-example-bug-payload-listing

   {"lastname": "student"}

The request leads to an internal server error with HTTP status code ``500``
as shown in
:numref:`errors-example-bug-response-listing`.

.. code-block:: json
   :caption: Response with error information
   :name: errors-example-bug-response-listing

   {
      "detail": [
         {
            "loc": [],
            "msg": "Internal Server Error",
            "type": "UdmError:APICommunicationError"
         }
      ]
   }

If you have the correlation ID,
for example from the ``X-Request-ID`` header,
you can search for it in the logs,
as shown in
:numref:`errors-example-bug-logs-correlation-listing`.
If you don't have the correlation ID,
try searching the Kelvin log for a correlation ID
that matches the time and arguments of your request.

.. code-block:: bash
   :caption: Show Kelvin logs for specific correlation ID
   :name: errors-example-bug-logs-correlation-listing

   grep .*89bbd1f5fe /var/log/univention/ucsschool-kelvin-rest-api/http.log

The first line in
:numref:`errors-example-bug-logs-correlation-lines-listing`
shows the Kelvin request to update the ``demo_student`` user,
which helps with debugging.

.. code-block::
   :caption: Example log lines for Kelvin with the correlation ID
   :name: errors-example-bug-logs-correlation-lines-listing

   2025-12-18 14:50:12 ERROR [199][89bbd1f5fe] main.udm_exception_handler:166  Encountered exception [HTTP 500]: for operation 'update' on 'users/user' with arguments {'users_user': {'options': {'pki': False, 'ucsschoolStudent': True, 'ucsschoolTeacher': False, 'ucsschoolStaff': False, 'ucsschoolAdministrator': False, 'ucsschoolExam': False, 'ucsschoolLegalGuardian': False}, 'position': 'cn=schueler,cn=users,ou=DEMOSCHOOL,dc=school,dc=test', 'properties': {'lastname': 'student', 'overridePWHistory': False, 'overridePWLength': False}}, 'dn': 'uid=demo_student,cn=schueler,cn=users,ou=DEMOSCHOOL,dc=school,dc=test'}: Internal Server Error responding with [{'loc': (), 'msg': 'Internal Server Error', 'type': 'UdmError:APICommunicationError'}]
   2025-12-18 14:50:12 INFO  [199][89bbd1f5fe] h11_impl.send:473  172.17.42.1:45752 - "PATCH /ucsschool/kelvin/v1/users/demo_student HTTP/1.1" 500

Examine the UDM HTTP REST API service logs
with the command in
:numref:`errors-example-bug-logs-udm-correlation-listing`.

.. code-block:: bash
   :caption: Show UDM HTTP REST API logs for specific correlation ID
   :name: errors-example-bug-logs-udm-correlation-listing

   grep .*89bbd1f5fe /var/log/univention/directory-manager-rest.log

In :numref:`errors-example-bug-logs-udm-correlation-lines-listing`
you can see an uncaught exception.

.. code-block::
   :caption: Example log lines for UDM HTTP REST API with the correlation ID
   :name: errors-example-bug-logs-udm-correlation-lines-listing

   2025-12-18T14:50:12.886964+01:00    ERROR [89bbd1f5fe] "Uncaught exception PATCH /udm/users/user/uid=demo_student,cn=schueler,cn=users,ou=DEMOSCHOOL,dc=school,dc=test (0.0.0.0) ...
   2025-12-18T14:50:12.889553+01:00    ERROR [89bbd1f5fe] 500 PATCH /udm/users/user/uid=demo_student,cn=schueler,cn=users,ou=DEMOSCHOOL,dc=school,dc=test (0.0.0.0) 25.44ms	| pid=555410 logname=tornado.access func=web.log_request:2279 requester_dn="cn=admin,dc=school,dc=test" requester_ip=172.17.0.1

The :file:`/var/log/univention/directory-manager-rest.log` log file contains the full Python traceback
in :numref:`errors-example-bug-logs-udm-traceback-listing`,
that includes the error message and source filename including the path.

In case you encounter an error indicated by a traceback in the Kelvin or UDM REST logs,
you can help Univention by opening a bug against the Kelvin component in
`Bugzilla <https://forge.univention.org/bugzilla/enter_bug.cgi?product=UCS%40school&component=HTTP-API%20%28Kelvin%29>`_.
To ensure that the developers have all the necessary information to work on the bug,
attach log files and describe how to reproduce the error and its impact.

.. code-block::
   :caption: Example for UDM log with Python traceback
   :name: errors-example-bug-logs-udm-traceback-listing

   [...]
     File "/usr/lib/python3/dist-packages/univention/admin/handlers/users/user.py", line 1253, in modify
       raise Exception("BUG!")
   Exception: BUG!
