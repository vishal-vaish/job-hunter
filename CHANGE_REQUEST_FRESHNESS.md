# Change Request: Job Freshness, Availability and Sorting

## Objective

The existing Autonomous Job Hunter project is already implemented.

Do NOT recreate the project.

Do NOT change the existing architecture unnecessarily.

Do NOT rewrite working components.

This change adds four requirements to the existing job-search pipeline:

1. Posting age
2. Job availability
3. Latest-first sorting
4. User-configurable maximum job age

The existing architecture and `AGENTS.md` remain the source of truth.

---

# 1. User Requirement: Maximum Job Age

The candidate must be able to specify how old a job posting can be.

Example:

```json
{
  "max_posting_age_days": 7
}
```

This means:

> Only jobs posted within the last 7 days should be considered.

Examples:

```text
max_posting_age_days = 1
→ jobs from the last 1 day

max_posting_age_days = 3
→ jobs from the last 3 days

max_posting_age_days = 7
→ jobs from the last 7 days

max_posting_age_days = 30
→ jobs from the last 30 days
```

This must be treated as a HARD FILTER.

The system must never include an older job just because it has a high relevance score.

---

# 2. Candidate Profile

Ensure the existing CandidateProfile supports:

```text
max_posting_age_days
```

Example:

```json
{
  "target_roles": [
    "Java Developer",
    "Backend Engineer"
  ],
  "skills": [
    "Java",
    "Spring Boot",
    "PostgreSQL",
    "REST",
    "React"
  ],
  "experience_years": 3,
  "locations": [
    "Delhi",
    "Noida",
    "Gurgaon"
  ],
  "work_modes": [
    "remote",
    "hybrid"
  ],
  "job_providers": [
    "linkedin"
  ],
  "max_posting_age_days": 7,
  "excluded_companies": [],
  "target_job_count": 20
}
```

Do not hardcode `7`.

The value must come from the candidate profile.

---

# 3. Posting Age

The current Job model should be extended to represent posting age.

Add fields appropriate to the existing architecture:

```text
posted_at
posted_age_days
posting_date_confidence
```

The exact implementation should follow the existing project's models and coding style.

---

# 4. Normalize Posting Information

Search providers may return different formats:

```text
Today
Just posted
1 hour ago
3 hours ago
1 day ago
2 days ago
5 days ago
1 week ago
2026-09-20
Sep 20, 2026
```

The system must normalize these into a common internal representation.

Preferred:

```text
posted_at
```

as a timezone-aware datetime whenever reliable information is available.

Also calculate:

```text
posted_age_days
```

when possible.

---

# 5. Do Not Invent Exact Dates

If the provider only gives:

```text
"1 week ago"
```

do not invent an exact timestamp.

Instead represent the information conservatively.

For example:

```text
posted_text = "1 week ago"
posted_age_days ≈ 7
posting_date_confidence = "medium"
```

If the posting age cannot be determined reliably:

```text
posting_date_confidence = "unknown"
```

Do not assume an unknown posting is recent.

---

# 6. Posting Age Filter

Add a deterministic freshness filter.

The logic must be equivalent to:

```text
job.posted_age_days <= candidate.max_posting_age_days
```

Example:

Candidate:

```text
max_posting_age_days = 7
```

Results:

```text
1 day old  → KEEP
3 days old → KEEP
7 days old → KEEP
8 days old → REJECT
15 days old → REJECT
30 days old → REJECT
```

This must happen in Python.

Do NOT ask the LLM to perform this calculation.

---

# 7. Unknown Posting Age

If posting age cannot be reliably determined:

```text
posted_age_days = unknown
```

The default behavior should be:

```text
REJECT from final current-job results
```

unless the existing architecture has an explicit policy that safely handles uncertain dates.

Do not silently treat unknown as `0 days`.

This is important because search engines can return stale indexed results.

---

# 8. Job Availability

Freshness is not enough.

A job can be:

```text
posted yesterday
but already closed.
```

Therefore add an availability state to the Job model.

Use a controlled set such as:

```text
UNKNOWN
ACTIVE
CLOSED
EXPIRED
REMOVED
```

The exact enum/model style should follow the existing project conventions.

---

# 9. Availability Verification

A job discovered by SearXNG is NOT automatically considered active.

The system must distinguish:

```text
Search Discovery
```

from:

```text
Availability Verification
```

Required pipeline:

```text
SearXNG
   ↓
Raw Search Result
   ↓
Normalize
   ↓
Deduplicate
   ↓
Posting Age Filter
   ↓
Availability Verification
   ↓
Hard Filters
   ↓
LLM Evaluation
   ↓
Final Results
```

---

# 10. Availability Evidence

A job should be marked unavailable when reliable evidence indicates that it is no longer open.

Examples:

```text
Job no longer available
Job has been closed
Position has been filled
Job expired
Job removed
No longer accepting applications
404 / removed job page
Provider explicitly reports closed
```

Use deterministic checks wherever possible.

Do not depend entirely on the LLM.

---

# 11. Availability Verification Strategy

Use the strongest available evidence.

Preferred order:

```text
1. Provider status
2. Direct job-page response
3. HTTP status
4. Page content indicators
5. Search result metadata
```

Examples:

```text
HTTP 404
→ unavailable

Page says "Job no longer available"
→ CLOSED

Page provides active application information
→ ACTIVE

No reliable evidence
→ UNKNOWN
```

Do not mark a job `ACTIVE` simply because SearXNG returned it.

---

# 12. Unknown Availability

If availability cannot be determined:

```text
availability_status = UNKNOWN
```

Default behavior:

```text
UNKNOWN
→ do not include in final active-job results
```

This prevents stale search-engine results from being presented to the candidate.

Keep the implementation configurable if the existing architecture already supports configuration.

---

# 13. Availability Timestamp

When availability is checked, store:

```text
availability_checked_at
```

This is useful for:

- debugging
- logging
- future refresh
- understanding when the job was verified

---

# 14. Remove Expired Jobs From Existing Results

This requirement applies not only to newly discovered jobs.

If the application already has stored jobs, they must not remain in the active result set after becoming invalid.

Example:

```text
Day 1
Java Developer
ACTIVE
```

Later:

```text
Day 4
Java Developer
CLOSED
```

The next refresh must remove it from the current active results.

Historical storage may retain the record for auditing/memory, but it must not appear as an active job.

---

# 15. Result Classification

Internally distinguish between:

```text
CURRENT
EXPIRED
CLOSED
REMOVED
UNKNOWN
```

Only:

```text
CURRENT
```

should normally appear in the final active job list.

Do not delete historical information unnecessarily.

Instead separate:

```text
historical records
```

from:

```text
current active jobs
```

where appropriate.

---

# 16. Latest Jobs First

The final job list must show the newest available jobs first.

Primary sorting:

```text
posted_at DESC
```

Meaning:

```text
newest
 ↓
oldest
```

Example:

```text
Posted 1 hour ago
Posted 3 hours ago
Posted 1 day ago
Posted 2 days ago
Posted 5 days ago
Posted 7 days ago
```

Do NOT sort primarily by LLM relevance score.

The candidate explicitly wants the latest available jobs.

---

# 17. Secondary Sorting

If two jobs have the same posting date/age, use a deterministic secondary ordering.

For example:

```text
evaluation score DESC
```

or another existing deterministic field.

Do not use random ordering.

---

# 18. Final Pipeline

The final pipeline must become:

```text
                    SEARCH
                      ↓
                  NORMALIZE
                      ↓
                 DEDUPLICATE
                      ↓
              POSTING AGE FILTER
                      ↓
           AVAILABILITY VERIFICATION
                      ↓
                HARD FILTERS
                      ↓
              LLM EVALUATION
                      ↓
                ACCEPT / REJECT
                      ↓
              SORT NEWEST FIRST
                      ↓
               FINAL RESULTS
```

The freshness and availability checks must happen BEFORE expensive LLM evaluation.

This avoids wasting Ollama tokens on jobs that are already invalid.

---

# 19. Interaction With Autonomous Brain

The Autonomous Brain must understand that:

```text
target_job_count
```

is a target.

It is NOT permission to violate freshness or availability constraints.

Example:

```text
target_job_count = 20
max_posting_age_days = 7
```

If only 6 valid jobs exist within the last 7 days:

```text
Return 6 valid jobs.
```

Do NOT return:

```text
6 fresh jobs
+
14 jobs older than 7 days
```

The Brain should instead try additional search strategies if it believes more fresh jobs may exist.

---

# 20. Agentic Response to Too Few Fresh Jobs

Example:

```text
Target = 20
Maximum age = 7 days

Search #1
→ 2 valid jobs

Brain observes:
Insufficient fresh jobs

Brain diagnoses:
Search strategy may be too narrow

Brain decides:
Try different role terminology

Search #2
→ 3 new valid jobs

Brain reflects:
Total = 5

Continue searching if useful.
```

Possible strategy changes:

```text
role terminology
keywords
location combinations
query structure
search breadth
```

Do not simply increase the allowed posting age.

The candidate's requested age limit is a hard constraint.

---

# 21. Example

Candidate:

```json
{
  "max_posting_age_days": 7,
  "target_job_count": 20
}
```

Search results:

| Job | Age | Availability | Action |
|---|---:|---|---|
| Java Developer A | 1 day | ACTIVE | Keep |
| Backend Engineer B | 2 days | ACTIVE | Keep |
| Java Developer C | 3 days | CLOSED | Reject |
| Java Developer D | 5 days | ACTIVE | Keep |
| Backend Engineer E | 8 days | ACTIVE | Reject — too old |
| Java Developer F | 1 day | UNKNOWN | Reject |
| Java Developer G | 6 days | ACTIVE | Keep |

Final:

```text
Java Developer A
Backend Engineer B
Java Developer D
Java Developer G
```

Sorted newest first.

---

# 22. LLM Responsibilities

The LLM should continue to handle:

```text
job semantic relevance
skill matching
role matching
candidate/job reasoning
search strategy generation
query generation
replanning
```

The LLM should NOT be responsible for:

```text
posting-age calculation
datetime arithmetic
HTTP status interpretation
deduplication
sorting
hard freshness filtering
hard availability filtering
filesystem security
```

Those remain deterministic Python responsibilities.

---

# 23. Hard Constraint Priority

The following constraints must be enforced before semantic scoring can make a job eligible:

```text
Provider
Posting age
Availability
Excluded company
Location/work mode where applicable
```

Example:

```text
LLM relevance score = 98

Posting age = 45 days
Candidate max age = 7 days
```

Result:

```text
REJECT
```

The relevance score must never override a hard freshness constraint.

---

# 24. Do Not Break Existing Architecture

Before modifying code:

1. Inspect the current implementation.
2. Identify the existing:
   - CandidateProfile
   - Job model
   - normalizer
   - deduplicator
   - filters
   - provider layer
   - GlobalSearch
   - Brain
   - evaluator
   - storage
3. Reuse existing components where possible.
4. Add only the missing pieces.
5. Preserve existing behavior unrelated to this change.
6. Do not rewrite the whole project.

---

# 25. Expected Changes

At minimum inspect whether these components need modification:

```text
models/candidate.py
models/job.py
pipeline/normalizer.py
pipeline/filters.py
providers/linkedin.py
search/global_search.py
agent/brain.py
storage/memory.py
```

If a dedicated availability verifier is appropriate for the existing architecture, create:

```text
pipeline/availability.py
```

or another appropriately named module.

Do not duplicate availability logic across providers and Brain.

---

# 26. Testing Requirements

Add tests for:

### Freshness

```text
1 day <= 7 days → accepted
7 days <= 7 days → accepted
8 days > 7 days → rejected
```

### Unknown age

```text
unknown posting age → rejected by default
```

### Availability

```text
ACTIVE → eligible
CLOSED → rejected
EXPIRED → rejected
REMOVED → rejected
UNKNOWN → rejected by default
```

### Sorting

Given:

```text
5 days
1 day
3 days
2 days
```

final order must be:

```text
1 day
2 days
3 days
5 days
```

### Combined filtering

A job must only reach final results when:

```text
fresh
AND
available
AND
passes hard filters
AND
passes semantic evaluation
```

---

# 27. Acceptance Criteria

The change is complete only when all of the following are true:

- Candidate can specify `max_posting_age_days`.
- Jobs older than that value are rejected.
- Posting age is normalized where possible.
- Unknown posting age is handled safely.
- Job availability is represented explicitly.
- Closed/expired/removed jobs are rejected.
- Unknown availability is not presented as active by default.
- Existing stale results are not presented as current jobs.
- Final jobs are sorted newest first.
- LLM relevance cannot override freshness.
- LLM relevance cannot override availability.
- Brain can search again when too few fresh jobs are found.
- Brain never relaxes the candidate's age constraint automatically.
- Target job count never overrides freshness/availability.
- Expensive LLM evaluation is not performed on obviously invalid jobs.
- Tests cover freshness, availability and sorting.
- Existing functionality continues to work.

---

# 28. Important Final Rule

The candidate's request:

> "Show me jobs from the last 7 days"

must mean exactly that.

It must NOT mean:

> "Prefer jobs from the last 7 days but show older jobs if necessary."

The system must respect the explicit freshness requirement.