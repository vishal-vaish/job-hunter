# 🧠 Agent Brain Architecture

> [!IMPORTANT]
> This document defines the responsibilities and behavior of the autonomous Master Brain.

---

# 🎯 1. Purpose

The Master Brain is the **orchestrator** of the autonomous job-hunting mission.

It decides:

* what is currently known
* what is missing
* what should happen next
* which agent/action should be used
* whether the mission should continue
* whether self-correction is required

It does not own every implementation detail.

---

# 🔄 2. Core ReAct Loop

```text
┌──────────────┐
│   OBSERVE    │
└──────┬───────┘
       ▼
┌──────────────┐
│  DIAGNOSE    │
└──────┬───────┘
       ▼
┌──────────────┐
│    DECIDE    │
└──────┬───────┘
       ▼
┌──────────────┐
│     ACT      │
└──────┬───────┘
       ▼
┌──────────────┐
│   REFLECT    │
└──────┬───────┘
       │
       └──────────────► OBSERVE
```

---

# 👁️ 3. OBSERVE

The Brain observes the current mission state.

It may inspect:

* discovered jobs
* rejected jobs
* search results
* errors
* pipeline state
* availability results
* agent outputs
* mission progress
* remaining work

Observation should describe **what happened**, not invent reasons.

---

# 🔬 4. DIAGNOSE

The Brain determines what the current state means.

Examples:

```text
No results
    ↓
Was search too narrow?
Was provider unavailable?
Were candidates rejected?
Was parsing unsuccessful?
```

The Brain should distinguish:

* no discovery
* discovery failure
* processing failure
* legitimate rejection
* insufficient evidence

---

# 🧭 5. DECIDE

The Brain chooses the next action.

Possible actions include:

* search again
* broaden a search strategy
* send candidates to evaluation
* retry a failed operation
* verify availability
* stop the mission
* report insufficient results

The Brain must remain within the architecture.

---

# ⚡ 6. ACT

The Brain invokes the appropriate capability.

```text
Discovery problem
      ↓
    Hunter

Evaluation problem
      ↓
   Auditor

Availability problem
      ↓
 Availability Pipeline
```

The Brain should not duplicate specialized logic unnecessarily.

---

# 🪞 7. REFLECT

After an action, the Brain evaluates the result.

Questions include:

* Did the action work?
* Did it produce useful information?
* Did it fail?
* Why did it fail?
* Is another attempt justified?
* Has the mission reached completion?

---

# 🔁 8. Self-Correction

Self-correction means:

> The Brain changes its **next action** based on observed results.

It does not mean:

> The Brain changes the architecture.

Example:

```text
Search attempt
      ↓
Few useful results
      ↓
Diagnose query problem
      ↓
Change search strategy
      ↓
Search again
```

This is valid self-correction.

Changing the responsibilities of Hunter or Auditor is an architectural change and requires user approval.

---

# 🎯 9. Candidate Intent Protection

The Brain must preserve the original candidate intent.

It may optimize **how** the search is performed.

It must not silently change **what the candidate wants**.

```text
Candidate Intent
      │
      ▼
Immutable Mission Requirements
      │
      ▼
Brain optimizes execution
```

---

# 🧩 10. Agent Boundaries

### 🛡️ Sentry

Observes mission/runtime conditions.

### 🔎 Hunter

Discovers potential jobs.

### 🧪 Auditor

Evaluates discovered jobs.

### ✅ Availability

Determines whether a posting remains open.

### 🧠 Brain

Coordinates the above capabilities.

---

# 🏁 11. Mission Completion

The Brain may finish when:

* sufficient valid jobs have been collected
* search opportunities are exhausted
* time/iteration limits are reached
* infrastructure prevents further progress
* no additional useful actions remain

Completion must be based on mission state, not arbitrary stopping.

---

# 🚨 12. Failure Recovery

Failures should be classified before retrying.

```text
Failure
  │
  ├── Temporary
  │      └── Retry may be appropriate
  │
  ├── Strategy
  │      └── Change next action
  │
  ├── Data
  │      └── Reject / quarantine candidate
  │
  └── Architectural
         └── STOP + request user approval
```

---

# 🔴 13. Architecture Protection

The Brain must never autonomously decide:

> "The architecture should be changed."

If the current architecture prevents a requested capability:

**STOP → REPORT → EXPLAIN → REQUEST APPROVAL**

---

# 🏁 Core Principle

> **The Brain controls the mission flow.**
>
> **It does not secretly redesign the system.**
