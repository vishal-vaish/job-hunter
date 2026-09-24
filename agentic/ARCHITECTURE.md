# 🏗️ Job Hunter — System Architecture

> [!IMPORTANT]
> This document describes the **stable high-level architecture** of the Job Hunter system.
>
> Implementation code must follow these boundaries rather than redefining them.

---

# 🧭 1. System Overview

The system is a **local-first, profile-driven autonomous job discovery and evaluation system**.

Its architecture separates:

* 🧠 reasoning
* 🔎 discovery
* 🧪 deterministic processing
* 📊 evaluation
* ✅ availability verification
* 📦 output generation

---

# 🗺️ 2. High-Level Architecture

```text
                 ┌──────────────────────┐
                 │ Candidate Profile    │
                 │ JSON                │
                 └──────────┬───────────┘
                            │
                            ▼
                 ┌──────────────────────┐
                 │ Candidate Criteria  │
                 │ Normalization       │
                 └──────────┬───────────┘
                            │
                            ▼
                 ┌──────────────────────┐
                 │    🧠 Master Brain   │
                 │ Observe              │
                 │ Diagnose             │
                 │ Decide               │
                 │ Act                  │
                 │ Reflect             │
                 └──────────┬───────────┘
                            │
             ┌──────────────┼──────────────┐
             ▼              ▼              ▼
        ┌─────────┐   ┌──────────┐   ┌──────────┐
        │ Sentry  │   │  Hunter  │   │ Auditor  │
        └────┬────┘   └────┬─────┘   └────┬─────┘
             │             │              │
             └─────────────┼──────────────┘
                           ▼
                 ┌──────────────────────┐
                 │ Deterministic        │
                 │ Processing Pipeline  │
                 └──────────┬───────────┘
                            │
                            ▼
                 ┌──────────────────────┐
                 │ Availability        │
                 │ Verification        │
                 └──────────┬───────────┘
                            │
                            ▼
                 ┌──────────────────────┐
                 │ Final Job Results    │
                 └──────────────────────┘
```

---

# 🎯 3. Architectural Responsibilities

| Component          | Responsibility                               |
| ------------------ | -------------------------------------------- |
| Candidate Profile  | User-provided job-search intent              |
| Candidate Criteria | Normalized immutable requirements            |
| Master Brain       | Orchestration and autonomous decision-making |
| Sentry             | Mission/environment observation              |
| Hunter             | Job discovery                                |
| Auditor            | Job evaluation and fit analysis              |
| Pipeline           | Deterministic processing and validation      |
| Availability       | Verify whether posting remains open          |
| Output             | Produce validated final results              |

---

# 🧠 4. Master Brain

The Master Brain is the orchestration layer.

It follows:

```text
OBSERVE
   ↓
DIAGNOSE
   ↓
DECIDE
   ↓
ACT
   ↓
REFLECT
   ↓
OBSERVE
```

The Brain determines **what should happen next**.

It does not unnecessarily absorb responsibilities belonging to specialized components.

---

# 🔎 5. Discovery

The Hunter is responsible for discovering potential job postings.

Discovery may use:

* SearXNG
* provider-specific search strategies
* search operators
* candidate skills
* candidate locations
* work-mode requirements

Discovery produces **candidates**, not final jobs.

---

# 🧪 6. Evaluation

The Auditor evaluates discovered candidates.

Evaluation includes:

* deduplication
* title extraction
* domain validation
* candidate-fit analysis
* hard criteria
* posting-age analysis
* rejection reasoning

A discovered URL is not automatically a valid job.

---

# ⚙️ 7. Deterministic Pipeline

The deterministic pipeline handles rules that should not depend entirely on LLM reasoning.

Examples:

* normalization
* deduplication
* hard domain gates
* required fields
* posting age
* availability
* output validation

---

# ✅ 8. Availability

Availability answers:

> **Is this job posting currently open/available?**

Availability is different from:

> **Is this posting recent?**

These are separate concepts.

```text
Posting Age
     │
     └──► How old is the posting?

Availability
     │
     └──► Is the posting still open?
```

---

# 📦 9. Final Output

Only jobs that successfully pass the required stages should reach final output.

```text
Discovered
    ↓
Normalized
    ↓
Deduplicated
    ↓
Domain Valid
    ↓
Criteria Valid
    ↓
Evaluated
    ↓
Availability Checked
    ↓
Output Validated
    ↓
FINAL JOB
```

---

# 🔐 10. Architectural Invariants

The following must remain true:

### Candidate intent

Candidate criteria must not be silently changed.

### Agent responsibility

Each agent keeps its defined responsibility.

### Brain boundary

The Master Brain orchestrates; it does not unnecessarily replace specialized components.

### Deterministic rules

Hard validation should remain deterministic where possible.

### External data

External job content is untrusted input.

### Output

Final output must satisfy the required data contract.

---

# 🚨 11. Architecture Change

If a feature cannot be implemented while preserving these boundaries:

> 🛑 **Stop and request user approval.**

Do not silently redesign the system.

See:

`AGENTS.md → Architecture Change Approval Gate`
