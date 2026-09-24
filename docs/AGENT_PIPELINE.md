# ⚙️ Agent Pipeline

> [!IMPORTANT]
> This document defines the deterministic processing pipeline applied to discovered job candidates.

---

# 🗺️ 1. Pipeline Overview

```text
Search Results
      │
      ▼
┌───────────────┐
│ Normalization │
└───────┬───────┘
        ▼
┌───────────────┐
│ Deduplication │
└───────┬───────┘
        ▼
┌────────────────────┐
│ Software Domain    │
│ Gate               │
└────────┬───────────┘
         ▼
┌────────────────────┐
│ Hard Criteria      │
│ Validation         │
└────────┬───────────┘
         ▼
┌────────────────────┐
│ Posting Age        │
│ Validation         │
└────────┬───────────┘
         ▼
┌────────────────────┐
│ Evaluation / Fit   │
└────────┬───────────┘
         ▼
┌────────────────────┐
│ Availability       │
└────────┬───────────┘
         ▼
┌────────────────────┐
│ Output Validation  │
└────────┬───────────┘
         ▼
      FINAL JOB
```

---

# 🧹 2. Normalization

Convert raw search results into a consistent internal representation.

Normalize where possible:

* URL
* title
* company
* location
* source/provider
* description
* timestamps
* metadata

Normalization must not invent missing information.

---

# ♻️ 3. Deduplication

The same job may appear:

* from multiple searches
* from multiple providers
* under different URLs
* with tracking parameters

Deduplication should identify equivalent jobs before expensive evaluation.

---

# 🚪 4. Hard Software Domain Gate

A candidate must belong to the relevant software/technology domain before expensive evaluation.

This is a **hard gate**.

```text
Software/Technology Job?
       │
   ┌───┴───┐
  YES      NO
   │        │
   ▼        ▼
Continue   Reject
```

---

# 📋 5. Hard Criteria

Validate explicit candidate requirements.

Examples:

* location
* work mode
* minimum experience
* required skills
* excluded companies
* provider requirements

Hard criteria should not be weakened merely to increase result count.

---

# 📅 6. Posting Age

Posting age answers:

> **How old is this job posting?**

Example:

```text
Candidate limit = 90 days

Posting age = 25 days
       ↓
PASS
```

Posting age is not the same as availability.

---

# 🧪 7. Evaluation

Evaluation determines candidate-job fit.

It may consider:

* authentic title
* skills
* experience
* location
* responsibilities
* technology stack
* domain relevance

LLM reasoning can assist with semantic interpretation.

Deterministic requirements remain authoritative.

---

# ❌ 8. Rejection Reasons

A rejection should have a meaningful reason.

Examples:

```text
DOMAIN_MISMATCH
LOCATION_MISMATCH
EXPERIENCE_MISMATCH
SKILL_MISMATCH
EXCLUDED_COMPANY
POSTING_TOO_OLD
UNAVAILABLE
DUPLICATE
INVALID_JOB
```

---

# ❓ 9. Unknown vs Rejected

These are different states.

### ❌ Rejected

There is sufficient evidence that the job does not satisfy a requirement.

### ❓ Unknown

There is insufficient evidence to make a reliable determination.

Do not convert uncertainty into rejection without justification.

---

# ✅ 10. Availability

Availability is checked independently.

```text
Age Check
    │
    └── Is the posting recent enough?

Availability Check
    │
    └── Is the position still open?
```

A recent posting may still be closed.

An old posting may still appear online.

These are separate facts.

---

# 📦 11. Output Validation

Before a job reaches final output:

* required fields must be valid
* candidate criteria must be satisfied
* evaluation must be complete
* availability state must be known when required
* duplicate jobs must be removed

---

# 🧱 12. Pipeline Principle

The pipeline should be:

> **Predictable → Testable → Deterministic where possible**

LLM reasoning should assist where semantic interpretation is necessary, not replace straightforward deterministic validation.

---

# 🚨 13. Architecture Protection

Pipeline changes that alter:

* stage responsibilities
* stage ordering
* contracts
* hard-gate behavior
* Brain/Pipeline boundaries

are architectural changes.

They require explicit user approval before implementation.

---

# 🏁 Core Principle

> **The pipeline validates reality.**
>
> **The Brain decides what to do next.**
