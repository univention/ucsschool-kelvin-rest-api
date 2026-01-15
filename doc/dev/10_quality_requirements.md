
>*There is currently no dedicated architecture documentation for the kelvin-api product. This document represents a first consolidated draft, structured according to the [arc42 template](https://arc42.org/overview).*

# 10. Quality Requirements

## 10.1 Performance Requirements

### 10.1.1 – Operation Classes

This chapter defines the operation classes used to specify performance, timing, and synchronization requirements.

---

#### DB Access Operations

These are **internal operation classes** (not API-facing) but extremely useful as **supporting quality requirements**.

##### DB – Read (Point Lookup)
  Single-row or primary-key lookup.

##### DB – Read (Range / Query)
  Indexed range queries, filtered queries, joins with bounded result sets.

##### DB – Write (Single Row / Transaction)
  Insert or update of one logical object in a single transaction.

##### DB – Write (Batch / Bulk)
  Batched inserts/updates (e.g. sync, resync, migrations).

---

#### API Operations

##### Read – Single Resource

Retrieval of one resource by identifier.

*Example:* `GET /ucsschool/kelvin/v2/schools/{school_name}`

##### Read – Collection (Simple Search)

Paginated and sorted list retrieval without additional filters.

*Example:* `GET /ucsschool/kelvin/v2/schools/?page=1&page_size=50&sort=name`

##### Read – Collection (Filtered Search)

Paginated and sorted list retrieval with one or more filters.

*Example:* `GET /ucsschool/kelvin/v2/users/?school=EXAMPLE_SCHOOL&roles=teacher&page=1&page_size=50&sort=lastname`

##### Write – Create

Creation of a new resource.

*Example:* `POST /ucsschool/kelvin/v2/users/`

##### Write – Partial Update

Partial modification of an existing resource.

*Example:* `PATCH /ucsschool/kelvin/v2/classes/{school}/{class_name}`

##### Write – Full Replace (Idempotent Update)

Full replacement of an existing resource.

*Example:* `PUT /ucsschool/kelvin/v2/workgroups/{school}/{workgroup_name}`

---

#### Synchronization Operations (Bidirectional)

All synchronization operation classes apply to **both directions**:

* **Nubus → Kelvin**
* **Kelvin → Nubus**

##### Sync – Propagation Latency (Regular / Background)

Time until a change in one system becomes visible in the other system.

*Examples:*

* Nubus change → visible via `GET /ucsschool/kelvin/v2/users/{username}`
* Kelvin change → visible in Nubus (e.g. new user)

##### Sync – Propagation Latency (Interactive / User-Wait)

Time until a change becomes visible in the other system **while a user is waiting for completion**.

*Examples:*

* Password reset triggered
* Workgroup membership changes

##### Sync – Processing Throughput (Steady State)

Processing rate during normal synchronization without backlog growth.

*Examples:*

* Continuous stream of Nubus updates processed by Kelvin
* Continuous stream of Kelvin updates processed by Nubus

##### Sync – Resynchronization / Catch-up

Bulk synchronization after outages or detected inconsistencies.

*Examples:*

* Full resync from Nubus to Kelvin after downtime
* Full resync from Kelvin to Nubus after connector restart

##### Sync – Outtake / Error Handling

Isolation, visibility, and retry of failed synchronization items.

*Examples:*

* Nubus → Kelvin update fails and is routed to outtake
* Kelvin → Nubus update fails and is retried later

---

### 10.1.2 Reference environments

Each environment must be reproducible via cfg files (OpenStack/KVM) and define dataset + infra sizing.

#### `MULTI_SERVER_MAX`

- Dataset/topology: (Pre-defined entities Schools, classes, workgroups, users, roles)
  - user: `200_000` (students) + `legal_wards` % + ... + 20% ()
- Infra sizing:
  - One DC primary node
  - `X` DC replicate nodes (one per school)
  - `Y` backup nodes

#### `SINGLE_SEVER_MAX`

- Dataset/topology:
  - Equals with `Multi_server_MAX`
- Infra sizing:
  - One DC primary node (no replicate node, no backup node)

> **TODO sync with PM/PS expectations**
> - [ ] Define Infra sizing (number `X` and `Y`)
> - [ ] Find realistic/full number of users (students, legal wards, legal guards, teachers, admins, ...)

### 10.1.3 API performance targets (MULTI_SERVER_MAX; draft)

> *About "draft": First let's define some numbers with our stakeholders.*
> *Then: Make a prototype and challenge/evaluate the numbers. (How far we are away? What can we control/tune vs. is +10% acceptable?)*

| Operation Class                     | Metric  | Target (p95) | Target (p99) | Notes / Assumptions         |
| ----------------------------------- | ------- | -----------: | -----------: | --------------------------- |
| Read – Single Resource              | Latency |     ≤ 300 ms |     ≤ 800 ms | By-id lookup, small payload |
| Read – Collection (Simple Search)   | Latency |     ≤ 800 ms |      ≤ 2.0 s | page_size=50, sort=1 field  |
| Read – Collection (Filtered Search) | Latency |      ≤ 1.2 s |      ≤ 3.0 s | ≤3 filters                  |
| Write – Create                      | Latency |      ≤ 1.2 s |      ≤ 3.0 s | Validation + single write   |
| Write – Partial Update              | Latency |      ≤ 1.2 s |      ≤ 3.0 s | PATCH semantics             |
| Write – Full Replace                | Latency |      ≤ 1.5 s |      ≤ 4.0 s | PUT, full validation        |


> **TODO sync with PM/PS expectations**
> - [ ] Confirm whether search needs separate thresholds from GET single. (often higher than single GET)
> - [ ] Define page size `N` and sorting keys for searches (per resource).

### 10.1.4 DB performance targets (MULTI_SERVER_MAX; draft)

> *About "draft": First let's define some numbers with our stakeholders.*
> *Then: Make a prototype and challenge/evaluate the numbers. (How far we are away? What can we control/tune vs. is +10% acceptable?)*

| Operation Class                       | Metric     |  Target (p95) |   Target (p99) | Notes                                  |
| --------------------------------------| -----------| ------------: | -------------: | ---------------------------------------|
| DB – Read (Point Lookup)              | Latency    |       ≤ 20 ms |        ≤ 50 ms | PK lookup, warm cache                  |
| DB – Read (Range / Query)             | Latency    |      ≤ 100 ms |       ≤ 300 ms | Indexed queries, bounded result set    |
| DB – Write (Single Row / Transaction) | Latency    |      ≤ 100 ms |       ≤ 300 ms | Single logical object, commit included |
| DB – Write (Batch / Bulk)             | Throughput |  ≥ 500 rows/s |   ≥ 200 rows/s | Batch size tuned, used for sync/resync |


## 10.2 Sync Requirements Nubus ↔ UCS@school (MULTI_SERVER_MAX; draft)

> *About "draft": First let's define some numbers with our stakeholders.*
> *Then: Make a prototype and challenge/evaluate the numbers. (How far we are away? What can we control/tune vs. is +10% acceptable?)*

| Operation Class                                       | Direction      | Metric            |   Target (p95) |   Target (p99) | Notes                            |
| ----------------------------------------------------- | -------------- | ----------------- | -------------: | -------------: | ---------------------------------|
| Sync – Propagation Latency (Regular / Background)     | Both           | Delay             |         ≤ 30 s |        ≤ 2 min | machine-to-machine               |
| Sync – Propagation Latency (Interactive / User-Wait)  | Both           | Delay             |          ≤ 2 s |          ≤ 5 s | User waits (e.g. password reset) |
| Sync – Processing Throughput                          | Both           | Items/sec         |           ≥ 20 |           ≥ 10 | Steady state, no backlog         |
| Sync – Resynchronization / Catch-up                   | Both           | Backlog drain     | ≤ 15 min / 10k | ≤ 30 min / 10k | After downtime                   |
| Sync – Outtake / Error Handling                       | Both           | Time to isolation |          ≤ 5 s |         ≤ 15 s | Failed items must not block      |
| Sync – Outtake / Error Handling                       | Both           | Retry success     |         ≥ 99 % |              — | After correction                 |

* Regular sync (machine to machine operations): sync typically made from school authority to school made nightly. Item to measure:
  * class and school sync (?)
  * `...`
* Interactive sync (user is waiting): syncs where a user waits for responses. Item to measure:
  * passwort reset
  * workgroups changes
  * `...`

> **TODO sync with PM/PS expectations**
> - [ ] Align `max delay` or `throughput` targets. (`throughput` is more common for queue like item processing.)
>   - [ ] Define the measurement window (“sustained for X minutes”) and load assumptions.
> - [ ] Define what counts as a "regular sync" (user/class/workgroup/…) and which operations as "interactive sync"
  > - [ ] "class and school sync" Is that really synced? Looks like at least classes are school dependend items

