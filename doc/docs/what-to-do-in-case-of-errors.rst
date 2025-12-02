What to do in case of errors
============================

When you encounter an error while using the Kelvin REST API, this can be for many different reasons:

- A service that Kelvin is depending on is unavailable or encounters itself an error when responding to a request from the Kelvin API.
- A UCS\@school object has been changed by another service without complying to the UCS\@school rules
- Kelvin is misconfigured
- A bug in Kelvin
- Network/Infrastructure problems

As a user, operator or developer of the Kelvin REST API

- Different reader groups
  user
  operator
  developer

Where are the relevant log files?

- With what can you work with? State of objects in LDAP and log files
- Reproducing the error


``/var/log/univention/ucsschool-kelvin-rest-api/``

``/var/log/univention/directory-manager-rest.log``

- logfiles
  - UDM
  - Kelvin
  - correlation id

How to read log files?
A log line examined for each relevant log file.
Log levels - what do they mean.

Example bug

Add code to UDM which has a chance to fail.

:external+uv-ucsschool-manual:doc:`UDM REST API<udm-rest-api>`

