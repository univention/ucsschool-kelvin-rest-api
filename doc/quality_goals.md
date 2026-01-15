
>*There is currently no dedicated architecture documentation for the kelvin-api product. This document represents a first consolidated draft, structured according to the [arc42 template](https://arc42.org/overview).*

## 1.2 Quality Goals

### Top quality goals (prioritized)
1. **Performance (primary driver for Kelvin v2)**
   - **API:** Read ≤ **10 ms**, Write ≤ **500 ms** (draft, from refinement)
   - **DB:** Read ≤ **10 ms**, Write ≤ **500 ms** (draft)
   - **Sync Nubus ↔ UCS@school:** bounded propagation delay + sustained processing capacity (targets per environment)

2. **Security**
   - Example: Auth required for all non-meta endpoints; least privilege enforced.

3. **Operability**
   - Example: Requests are observable (correlation IDs, latency/error metrics) to enable performance engineering.

4. **Maintainability**
   - Example: Requirements are defined via **few environments** + **operation catalog** (avoid per-endpoint duplication).

> Details and testable thresholds are specified in **Chapter 10: Quality Requirements**.

---

## 10. Quality Requirements

### 10.1 Performance Requirements

#### 10.1.1 Measurement conventions (applies to DB/API)
- **Operation classes**
  - **Read (R-Single):** GET single
    - **Read (R-Multi):** GET search (paginated/sorted)
  - **Write (W):** POST / PUT / PATCH / DELETE
- **Reporting**: p95 (define percentile used for pass/fail)
- **Warm-up**: `<define warm-up policy>`
- **Error budget**: `<define allowed error rate>`

> **TODO**
> - [x] Define “UI timing point” (TTFB vs first render vs fully interactive).
>   - [x] Remove UI measurements!

#### 10.1.2 Reference environments
Each environment must be reproducible via cfg files (OpenStack/KVM) and define dataset + infra sizing.

1. **MULTI_SERVER_MAX**
   - Dataset/topology: (Pre-defined entities Schools, classes, workgroups, users, roles)
      - user: `200_000` (students) + `legal_wards` % + ... + 20% ()
   - Infra sizing:
      - One DC primary node
      - `X` DC replicate nodes (one per school)
      - `Y` backup nodes
2. **SINGLE_SEVER_MAX**
    - Dataset/topology:
      - Equals with `Multi_server_MAX`
    - Infra sizing:
      - One DC primary node (no replicate node, no backup node)


**TODO sync with PM/PS expectations**
- [ ] Define Infra sizing (number `X` and `Y`)
- [ ] Find realistic/full number of users (students, legal wards, legal guards, teachers, admins, ...)

#### 10.1.3 API performance targets (MULTI_SERVER_MAX; draft)

> *About "draft": First let's define some numbers with our stakeholders.*
> *Then: Make a prototype and challenge/evaluate the numbers. (How far we are away? What can we control/tune vs. is +10% acceptable?)*

| Resource | Search (page=N, sorted)<br/>no filter | Search (page=N, sorted)<br/>filtered | GET single | POST | PUT | PATCH |
|---|---:|---:|---:|---:|---:|---:|
| schools | ≤ 10 ms | ≤ 10 ms | ≤ 10 ms | ≤ 500 ms | N/A | N/A |
| classes | ≤ 10 ms | ≤ 10 ms | ≤ 10 ms | ≤ 500 ms | ≤ 500 ms | ≤ 500 ms |
| workgroups | ≤ 10 ms | ≤ 10 ms | ≤ 10 ms | ≤ 500 ms | ≤ 500 ms | ≤ 500 ms |
| users | ≤ 10 ms | ≤ 10 ms | ≤ 10 ms | ≤ 500 ms | ≤ 500 ms | ≤ 500 ms |
| roles | ≤ 10 ms | N/A | ≤ 10 ms | N/A | N/A | N/A |

> **TODO sync with PM/PS expectations**
> - [ ] Confirm whether search needs separate thresholds from GET single. (often higher than single GET)
> - [ ] Define page size `N` and sorting keys for searches (per resource).

#### 10.1.4 DB performance targets (MULTI_SERVER_MAX; draft)

> *About "draft": First let's define some numbers with our stakeholders.*
> *Then: Make a prototype and challenge/evaluate the numbers. (How far we are away? What can we control/tune vs. is +10% acceptable?)*

| Operation class | Target |
|---|---:|
| DB read (R) | ≤ `10` ms |
| DB write (W) | ≤ `500` ms |

### 10.2 Sync Requirements Nubus ↔ UCS@school (MULTI_SERVER_MAX; draft)

> *About "draft": First let's define some numbers with our stakeholders.*
> *Then: Make a prototype and challenge/evaluate the numbers. (How far we are away? What can we control/tune vs. is +10% acceptable?)*

| Direction | Target<br/>regular sync | Target<br/>interactive sync
|---|---:|---:|
| Nubus → UCS@school (visible via Kelvin reads) | ≤ `<T>` ms <br/>or ≥ `<items/sec>` | ≤ `<T>` ms <br/>or ≥ `<items/sec>` |
| UCS@school → Nubus | ≤ `<T>` ms <br/>or ≥ `<items/sec>` | ≤ `<T>` ms <br/>or ≥ `<items/sec>` |

* Regular sync (machine to machine operations): sync typically made from school authority to school made nightly. Item to measure:
  * class and school sync
  * `...`
* Interactive sync (user is waiting): syncs where a user waits for responses. Item to measure:
  * passwort reset
  * workgroups changes
  * `...`

> **TODO sync with PM/PS expectations**
> - [ ] Align `max delay` or `throughput` targets. (`throughput` is more common for queue like item processing.)
>   - [ ] Define the measurement window (“sustained for X minutes”) and load assumptions.
> - [ ] Define what counts as a “tegular sync” (user/class/workgroup/…) and which operations as "interactive sync"

