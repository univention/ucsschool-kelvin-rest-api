## 1.2 Quality Goals

### Top quality goals (prioritized)
1. **Performance (primary driver for Kelvin v2)**
   - **API:** Read ≤ **10 ms**, Write ≤ **500 ms** (draft, from refinement)
   - **DB:** Read ≤ **10 ms**, Write ≤ **500 ms** (draft)
   - **UI (E2E):** Read ≤ **10 ms**, Write ≤ **500 ms** (draft; UI timing definition pending)
   - **Sync Nubus ↔ UCS@school:** bounded propagation delay + sustained processing capacity (targets per environment)

2. **Security**
   - Auth required for all non-meta endpoints; least privilege enforced.

3. **Operability**
   - Requests are observable (correlation IDs, latency/error metrics) to enable performance engineering.

4. **Maintainability**
   - Requirements are defined via **few environments** + **operation catalog** (avoid per-endpoint duplication).

> Details and testable thresholds are specified in **Chapter 10: Quality Requirements**.


---

## 10. Quality Requirements

### 10.1 Performance Requirements

#### 10.1.1 Measurement conventions (applies to DB/API/UI)
- **Operation classes**
  - **Read (R):** GET single + GET search (paginated/sorted)
  - **Write (W):** POST / PUT / PATCH / DELETE
- **Reporting**: `<p95 recommended>` (define percentile used for pass/fail)
- **Warm-up**: `<define warm-up policy>`
- **Error budget**: `<define allowed error rate>`

**TODO**
- [ ] Decide percentile for pass/fail (p95 recommended; optionally also track p99).
- [ ] Define “UI timing point” (TTFB vs first render vs fully interactive).

#### 10.1.2 Reference environments
Each environment must be reproducible via cfg files (OpenStack/KVM) and define dataset + infra sizing.

- **ENV_MAX (primary)**
  - Dataset/topology: `<schools/users/groups/memberships…>`
  - Infra sizing: `<API/LDAP/DB resources + network assumptions>`
  - Load profile: `<concurrency + request mix>`

**TODO**
- [ ] Define ENV_MAX dataset numbers and topology.
- [ ] Define page size `N` and sorting keys for searches (per resource).

#### 10.1.3 API performance targets (ENV_MAX; draft)
> Search must be **paginated and sorted** (page size `N` and sort keys defined in ENV_MAX).

| Resource | Search (page=N, sorted) no filter | Search (page=N, sorted) filtered | GET single | POST | PUT | PATCH |
|---|---:|---:|---:|---:|---:|---:|
| schools | ≤ 10 ms | ≤ 10 ms | ≤ 10 ms | ≤ 500 ms | N/A | N/A |
| users | ≤ 10 ms | ≤ 10 ms | ≤ 10 ms | ≤ 500 ms | ≤ 500 ms | ≤ 500 ms |
| classes | ≤ 10 ms | ≤ 10 ms | ≤ 10 ms | ≤ 500 ms | ≤ 500 ms | ≤ 500 ms |
| workgroups | ≤ 10 ms | ≤ 10 ms | ≤ 10 ms | ≤ 500 ms | ≤ 500 ms | ≤ 500 ms |
| roles | ≤ 10 ms | N/A | ≤ 10 ms | N/A | N/A | N/A |

**TODO**
- [ ] Confirm whether search needs separate thresholds from GET single. (often higher than single GET)

#### 10.1.4 DB performance targets (ENV_MAX; draft)
| Operation class | Target |
|---|---:|
| DB read (R) | ≤ `<T>` ms |
| DB write (W) | ≤ `<T>` ms |

#### 10.1.5 UI timing targets (ENV_MAX; draft)
| Operation class | Target | Timing point |
|---|---:|---|
| UI read (R) | ≤ `<T>` ms | `<define: TTFB / first content / fully interactive>` |
| UI write (W) | ≤ `<T>` ms | `<define: “success visible + state updated”>` |


### 10.2 Sync Requirements (Nubus ↔ UCS@school)

Sync targets are defined **per direction**, because each direction can have different pipelines/bottlenecks.

#### 10.2.1 Propagation delay (latency) — ENV_MAX
| Direction | Target |
|---|---:|
| Nubus → UCS@school (visible via Kelvin reads) | ≤ `<T>` |
| UCS@school → Nubus | ≤ `<T>` |

#### 10.2.2 Processing capacity (throughput) — ENV_MAX
| Direction | Target | Notes |
|---|---:|---|
| Nubus → UCS@school | ≥ `<items/sec>` | sustained (steady-state) |
| UCS@school → Nubus | ≥ `<items/sec>` | sustained (steady-state) |

**TODO**
- [ ] Define what counts as a “sync item” (user/class/workgroup/…).
- [ ] Define the measurement window (“sustained for X minutes”) and load assumptions.
- [ ] Align max delay + throughput targets with PM/PS expectations.


### 10.3 Security Requirements (brief)
- Non-meta endpoints require auth; unauthorized access must be rejected.
- Authorization respects school/role boundaries (no cross-OU leakage).

**TODO**
- [ ] Confirm whether docs/readme/changelog endpoints are public or require auth.


### 10.4 Operability Requirements (brief)
- Correlation ID present for every request; logged and propagated.
- Basic metrics exist per endpoint profile: latency percentiles, error rate, throughput.

### 10.5 Maintainability Requirements (brief)
- Requirements are expressed via **environments + operation catalog** (no per-endpoint prose).
- Adding a resource should require only updating the API target table + test scenarios mapping.
