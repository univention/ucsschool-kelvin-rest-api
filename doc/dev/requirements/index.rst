.. SPDX-FileCopyrightText: 2026 Univention GmbH
..
.. SPDX-License-Identifier: AGPL-3.0-only

Requirements
============

This section captures the requirements the UCS\@school Kelvin REST API must
satisfy. It exists to give a single source of reference for what the system
has to do and how well it has to do it, so that design decisions, use cases,
and tests can point back to a named requirement.

Requirements are split into two chapters:

:doc:`requirements-functional`
   *What* the system does — capabilities, business rules, authentication and
   authorization, synchronization behavior, and integration.

:doc:`requirements-nonfunctional`
   *How well* the system does it — performance, scalability, availability,
   security, reliability, maintainability, and compatibility.

Each requirement is given a stable identifier — ``FR-NNN`` for functional and
``NFR-XNN`` for non-functional requirements — so it can be referenced from use
cases (:doc:`../usecases`), architecture decisions, and test cases. Identifiers
are never reused once assigned.

.. note::

   Many requirements are still drafts. Performance targets in particular are
   provisional and must be agreed with stakeholders before they are treated as
   binding SLOs.

.. toctree::
   :maxdepth: 2

   requirements-functional
   requirements-nonfunctional
