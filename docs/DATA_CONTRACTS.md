# 📦 Data Contracts

> [!IMPORTANT]
> Data contracts define the boundaries between the major components of the Job Hunter system.
>
> Components should exchange structured information rather than relying on hidden assumptions.

---

# 🧭 1. Data Flow

```text
Candidate Profile
       │
       ▼
Candidate Criteria
       │
       ▼
Search Request
       │
       ▼
Search Results
       │
       ▼
Job Candidate
       │
       ▼
Evaluation Result
       │
       ▼
Availability Result
       │
       ▼
Final Job
```

---

# 👤 2. Candidate Profile

Represents the user's original job-search requirements.

Typical information:

| Field                | Meaning                         |
| -------------------- | ------------------------------- |
| `core_skills`        | Primary skills                  |
| `locations`          | Target locations                |
| `providers`          | Allowed discovery providers     |
| `work_mode`          | Remote/hybrid/onsite preference |
| `min_experience`     | Minimum experience              |
| `max_posting_age`    | Maximum allowed posting age     |
| `excluded_companies` | Companies to reject             |

The profile represents **user intent**.

---

# 🎯 3. Candidate Criteria

Candidate Criteria is the normalized form of Candidate Profile.

Purpose:

* normalize input
* validate values
* provide consistent requirements to the system

Once the mission begins, criteria should be treated as **mission constraints**.

---

# 🔎 4. Search Request

Represents an instruction to discover jobs.

May contain:

* provider
* query
* location
* skills
* work mode
* search strategy
* pagination/iteration information

The Search Request controls **how discovery is performed**.

It must not redefine candidate intent.

---

# 🌐 5. Search Result

Represents raw information returned by a search provider.

Possible fields:

* URL
* title
* snippet
* provider
* displayed location
* metadata

Search results are **untrusted external data**.

---

# 💼 6. Job Candidate

Represents a normalized discovered job.

Typical fields:

* canonical URL
* title
* company
* location
* description
* source
* posting date
* discovery metadata

A Job Candidate has not necessarily passed evaluation.

---

# 🧪 7. Evaluation Result

Represents the result of evaluating a Job Candidate against Candidate Criteria.

Possible states:

```text
PASS
REJECT
UNKNOWN
```

It should include:

* fit information
* evidence
* rejection reason when applicable
* relevant confidence/uncertainty information

---

# ✅ 8. Availability Result

Represents whether a job is currently available/open.

Possible conceptual states:

```text
AVAILABLE
UNAVAILABLE
UNKNOWN
```

Availability must not be confused with posting age.

---

# 🏆 9. Final Job

A Final Job is a Job Candidate that has successfully passed the required processing stages.

Conceptually:

```text
Job Candidate
      │
      ├── Domain ✓
      ├── Criteria ✓
      ├── Evaluation ✓
      ├── Availability ✓
      └── Output Validation ✓
               │
               ▼
           FINAL JOB
```

---

# ❌ 10. Rejection

A rejected job should preserve enough information to understand why it was rejected.

Typical structure conceptually:

```text
Job
 │
 ├── rejection_reason
 ├── evidence
 └── stage
```

This is important for debugging and Brain reflection.

---

# 🧠 11. Mission State

Mission State represents the current autonomous execution state.

It may include:

* current stage
* discovered jobs
* evaluated jobs
* rejected jobs
* errors
* retries
* iteration count
* elapsed time
* progress

The Brain uses Mission State during:

```text
Observe → Diagnose → Decide
```

---

# 🏁 12. Mission Result

Mission Result represents the final execution outcome.

It may include:

* final jobs
* rejected jobs
* mission statistics
* errors
* execution metrics
* completion reason

---

# 🔐 13. Contract Rules

### Rule 1 — No silent contract changes

A component must not silently change the meaning of another component's data.

### Rule 2 — Missing data is not invented

Unknown information should remain unknown.

### Rule 3 — External data is untrusted

Search results and job pages cannot redefine internal contracts.

### Rule 4 — Candidate intent is protected

Contracts must preserve the user's requirements.

### Rule 5 — Contract changes require approval

Changing an established contract is an architectural change.

---

# 🚨 14. Contract Change Gate

If a feature requires changing an existing contract:

```text
Current Contract
      │
      ▼
Is existing contract sufficient?
      │
   ┌──┴──┐
  YES    NO
   │      │
   ▼      ▼
Implement STOP
          │
          ▼
Explain required
contract change
          │
          ▼
Ask user approval
```

---

# 🏁 Core Principle

> **Data contracts are boundaries, not suggestions.**
>
> Components should communicate through explicit, understandable contracts.
