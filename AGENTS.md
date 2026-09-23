# Autonomous Job Hunter — AI Development Instructions

## 1. Project Goal

Build a local-first autonomous job-hunting system.

The system accepts a candidate profile, understands the candidate's requirements, creates a search mission, searches for jobs through SearXNG, evaluates discovered jobs against the candidate profile, learns from search results, changes its search strategy when necessary, and produces a final list of relevant jobs.

The system must operate locally.

Primary infrastructure:

- Ollama: `http://localhost:11434`
- SearXNG: `http://localhost:8081`
- Current job provider: LinkedIn
- Future providers: Indeed, Naukri, etc.

Do NOT use Docker.

---

# 2. Critical Architecture Rule

Do NOT build a swarm of independent LLM agents.

The system uses:

> One Python-controlled Autonomous Brain + deterministic tools + local LLM.

The Python application controls:

- state
- memory
- iterations
- tool execution
- search
- deduplication
- filtering
- persistence
- security
- stopping conditions

The local LLM is used selectively for:

- natural-language candidate understanding
- mission generation
- search-query generation
- search strategy adaptation
- semantic job evaluation

The LLM must never directly control the filesystem, shell, network, or arbitrary Python execution.

---

# 3. High-Level Flow

The complete system follows this flow:

User
 ↓
Conversation / Candidate Input
 ↓
Candidate Profile
 ↓
Profile Validation
 ↓
Mission Generator
 ↓
Autonomous Brain
 ↓
OBSERVE
 ↓
DIAGNOSE
 ↓
DECIDE
 ↓
ACT
 ↓
Search Jobs
 ↓
SearXNG
 ↓
LinkedIn Provider
 ↓
Raw Search Results
 ↓
Normalize
 ↓
Deduplicate
 ↓
Hard Filters
 ↓
LLM Job Evaluation
 ↓
Accept / Reject
 ↓
Memory
 ↓
REFLECT
 ↓
Replan OR Stop
 ↓
Final Jobs
 ↓
sandbox/output/jobs.json

The Brain is responsible for controlling this loop.

---

# 4. Autonomous Brain

The Brain is the central orchestrator.

Its loop is:

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
REPEAT or STOP
```

This must be a real feedback loop.

Do NOT implement:

```text
for query in queries:
    search(query)
```

and call that agentic behavior.

The Brain must inspect the result of previous actions.

For example:

```text
Iteration 1
Search "Java Developer Delhi"
        ↓
Only 2 relevant jobs
        ↓
Diagnose: insufficient results
        ↓
Decide: broaden role terminology
        ↓
Search "Backend Engineer Delhi"
```

Another example:

```text
Search query A
        ↓
Mostly senior jobs
        ↓
Diagnose: experience mismatch
        ↓
Decide: add junior/mid-level terminology
        ↓
Generate new query
```

Another:

```text
Search query
        ↓
Many duplicate URLs
        ↓
Diagnose: poor query diversity
        ↓
Change query strategy
```

The Brain must remember previous queries and URLs so it does not repeatedly perform the same action.

---

# 5. Candidate Profile

Candidate information must be represented internally as structured data.

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
  "max_posting_age_days": 30,
  "excluded_companies": [],
  "target_job_count": 20
}
```

The candidate profile is internal data.

Do not expose implementation-specific JSON requirements to the end user unnecessarily.

---

# 6. Mission

The candidate profile is converted into a Search Mission.

The Mission contains:

- objective
- allowed providers
- search roles
- keywords
- locations
- work modes
- posting-age requirements
- excluded companies
- evaluation threshold
- minimum target jobs
- maximum iterations

The Mission is a plan.

The Brain is responsible for executing and adapting that plan.

---

# 7. Search Architecture

The Brain must NOT directly know provider-specific implementation details.

Use:

```text
Brain
  ↓
Search Tool
  ↓
Global Search
  ↓
Provider Router
  ↓
LinkedIn Provider
  ↓
SearXNG
```

The current provider is:

```text
LinkedIn
```

LinkedIn discovery is performed through SearXNG.

The LinkedIn provider must not directly implement browser automation or unrestricted scraping.

Future providers must be pluggable.

Example:

```text
providers/
├── base.py
├── linkedin.py
├── indeed.py
└── naukri.py
```

Adding a new provider must not require rewriting the Brain.

---

# 8. SearXNG

SearXNG is the discovery/search layer.

Ollama must NOT perform web searches.

The LLM generates a search strategy/query.

Python sends that query to SearXNG.

Example:

```text
LLM
 ↓
"Java Spring Boot backend developer Delhi 3 years"
 ↓
Python Search Tool
 ↓
SearXNG
 ↓
Search Results
```

The LLM must never receive unrestricted HTTP/network tools.

---

# 9. LLM Tool Boundary

The local model must NOT have generic tools such as:

```text
read_file
write_file
delete_file
run_shell
run_python
execute_command
powershell
cmd
os.listdir
arbitrary HTTP
```

Do not expose these to the model.

Instead expose narrow application-level operations such as:

```text
search_jobs
read_memory
write_memory
save_results
```

Each tool must enforce its own permissions.

---

# 10. Filesystem Security

The application uses an application-level sandbox.

The sandbox is:

```text
sandbox/
├── input/
├── output/
├── memory/
├── logs/
└── workspace/
```

Permissions:

| Directory | Permission |
|---|---|
| `input/` | read |
| `output/` | read/write |
| `memory/` | read/write |
| `logs/` | append/write |
| `workspace/` | read/write |

The agent must not access:

```text
project source files
.env
.git
Windows filesystem
user home directory
SSH keys
browser data
other projects
arbitrary paths
```

The sandbox resolver must prevent:

- absolute paths
- `../` traversal
- symlink escape
- junction/reparse-point escape where applicable

All agent filesystem access must go through the Sandbox abstraction.

---

# 11. Important Security Principle

The model does not need direct filesystem access.

Python owns the filesystem.

The model requests an allowed operation.

Python validates and executes it.

Correct:

```text
LLM
 ↓
purpose-specific tool
 ↓
Sandbox
 ↓
filesystem
```

Incorrect:

```text
LLM
 ↓
arbitrary Python
 ↓
filesystem
```

---

# 12. Memory

The Brain must maintain persistent memory.

Memory should track at minimum:

```text
searched_queries
searched_urls
accepted_urls
rejected_urls
failed_queries
iteration
search statistics
```

Memory exists to prevent repetitive behavior.

For example, if:

```text
"Java Developer Delhi"
```

was already searched, the Brain should not blindly search the exact same query again.

Instead it should change strategy.

Memory must persist between iterations.

Store it under:

```text
sandbox/memory/
```

---

# 13. Job Processing Pipeline

Every discovered result should pass through:

```text
Raw Result
 ↓
Normalize
 ↓
Deduplicate
 ↓
Hard Filters
 ↓
LLM Evaluation
 ↓
Accept / Reject
```

## Normalize

Convert provider-specific results into a common Job model.

## Deduplicate

Deduplicate primarily by normalized URL.

Also account for obvious URL variations.

## Hard Filters

Apply deterministic rules such as:

- excluded companies
- provider restrictions
- obvious location constraints
- posting-age constraints when reliable data exists
- work-mode constraints when reliable data exists

Do not ask the LLM to perform simple deterministic filtering when Python can do it reliably.

## LLM Evaluation

Use the LLM for semantic matching:

```text
candidate
+
job
↓
evaluation
```

Return structured data such as:

```json
{
  "score": 87,
  "suitable": true,
  "reasons": [
    "Strong Java and Spring Boot match",
    "Experience requirement is compatible"
  ],
  "matched_skills": [
    "Java",
    "Spring Boot",
    "PostgreSQL"
  ],
  "missing_skills": []
}
```

The LLM must not invent information that is not present in the candidate or job.

---

# 14. Job Model

Use a provider-independent Job model.

Minimum fields:

```text
provider
title
company
location
url
description
posted_text
search_query
```

Provider-specific data should not leak into the core Brain.

---

# 15. Agent Tools

Agent tools should be narrow and purpose-specific.

Expected tools:

```text
agent/tools/
├── search_jobs.py
├── memory.py
└── results.py
```

### Search Tool

Purpose:

```text
Search for jobs through GlobalSearch.
```

It must not provide arbitrary HTTP access.

### Memory Tool

Purpose:

```text
Read/write agent memory.
```

It must only access:

```text
sandbox/memory/
```

### Results Tool

Purpose:

```text
Persist final accepted jobs.
```

It must only write to:

```text
sandbox/output/
```

---

# 16. Project Structure

Use this architecture:

```text
job-hunter/
│
├── AGENTS.md
├── README.md
├── main.py
├── requirements.txt
├── .env
├── .env.example
│
├── config/
│   ├── __init__.py
│   └── settings.py
│
├── models/
│   ├── __init__.py
│   ├── candidate.py
│   ├── mission.py
│   ├── job.py
│   └── evaluation.py
│
├── agent/
│   ├── __init__.py
│   ├── brain.py
│   ├── mission_generator.py
│   ├── profile_validator.py
│   ├── evaluator.py
│   │
│   └── tools/
│       ├── __init__.py
│       ├── search_jobs.py
│       ├── memory.py
│       └── results.py
│
├── providers/
│   ├── __init__.py
│   ├── base.py
│   └── linkedin.py
│
├── search/
│   ├── __init__.py
│   └── global_search.py
│
├── pipeline/
│   ├── __init__.py
│   ├── normalizer.py
│   ├── deduplicator.py
│   └── filters.py
│
├── infrastructure/
│   ├── __init__.py
│   ├── ollama.py
│   └── searxng.py
│
├── storage/
│   ├── __init__.py
│   └── memory.py
│
├── security/
│   ├── __init__.py
│   └── sandbox.py
│
├── utils/
│   ├── __init__.py
│   └── logger.py
│
└── sandbox/
    ├── input/
    ├── output/
    ├── memory/
    ├── logs/
    └── workspace/
```

---

# 17. Separation of Responsibilities

## LLM

Responsible for:

```text
understanding
reasoning
semantic interpretation
mission generation
query generation
replanning
job semantic evaluation
```

## Python

Responsible for:

```text
orchestration
state
memory
iterations
tools
HTTP
SearXNG
provider routing
deduplication
hard filters
filesystem
security
persistence
logging
```

Never move security-critical or deterministic responsibilities into the LLM.

---

# 18. Error Handling

The system must not crash because:

- Ollama temporarily fails
- SearXNG returns no results
- a provider result is malformed
- one job cannot be evaluated
- a query returns zero results
- JSON from the LLM is malformed
- a duplicate URL is encountered

The system should:

1. log the failure
2. update memory/state
3. diagnose the situation
4. change strategy when appropriate
5. continue if possible
6. stop cleanly when continuation is no longer useful

---

# 19. LLM Output Rules

Whenever the LLM is asked to produce structured data:

- request JSON only
- validate with Pydantic
- reject malformed output
- do not blindly trust model output
- retry with a corrected prompt when appropriate
- impose size limits
- never execute model-generated code

The model's output is untrusted input.

---

# 20. Stopping Conditions

The Brain should stop when one of these occurs:

```text
target job count reached
OR
maximum iterations reached
OR
maximum execution time reached
OR
no useful search strategy remains
```

Do not continue searching indefinitely.

---

# 21. Agentic Behavior Requirements

The implementation must demonstrate actual adaptation.

The Brain should be capable of changing:

- role terminology
- keywords
- location combinations
- query structure
- search breadth
- search strategy

based on previous outcomes.

Examples:

```text
Poor result count
→ broaden query
```

```text
Too many senior jobs
→ modify experience terminology
```

```text
Too many duplicates
→ generate more diverse queries
```

```text
Good result count but low semantic match
→ improve keyword/role strategy
```

```text
Target reached
→ stop
```

---

# 22. No Fake Agentic Behavior

Do not implement fake behavior such as:

```text
iteration = 1
search query
iteration = 2
search another hardcoded query
iteration = 3
stop
```

The next action must depend on observed state.

The system must be able to explain internally why it is changing strategy.

---

# 23. Development Rules

When modifying the project:

1. Inspect the existing implementation first.
2. Preserve working functionality.
3. Do not rewrite unrelated files.
4. Do not introduce unnecessary dependencies.
5. Keep components loosely coupled.
6. Keep provider-specific logic inside providers.
7. Keep filesystem access inside Sandbox.
8. Keep deterministic logic in Python.
9. Keep semantic reasoning in the LLM.
10. Validate all LLM output.
11. Add logging around important state transitions.
12. Never bypass the sandbox for convenience.

---

# 24. Implementation Order

Implement the system in this order:

### Phase 1 — Foundation

- configuration
- models
- Ollama client
- SearXNG client
- sandbox
- logger

### Phase 2 — Search

- provider abstraction
- LinkedIn provider
- GlobalSearch
- normalization
- deduplication
- filters

### Phase 3 — Intelligence

- profile validator
- mission generator
- job evaluator

### Phase 4 — Agent

- memory
- agent tools
- Autonomous Brain
- OBSERVE → DIAGNOSE → DECIDE → ACT → REFLECT

### Phase 5 — Persistence

- candidate input
- memory persistence
- final results
- logging

### Phase 6 — Conversation/UI

Only after the core autonomous engine works:

```text
User conversation
 ↓
Candidate Profile
 ↓
Mission
 ↓
Autonomous Brain
```

The UI must not contain the core job-search logic.

---

# 25. Current MVP Scope

The first working version should support:

```text
Candidate Profile
+
LinkedIn
+
SearXNG
+
Ollama
+
Autonomous Brain
+
Job Evaluation
+
Persistent Memory
+
Sandbox
+
JSON output
```

Do not add:

- browser automation
- CAPTCHA bypass
- unrestricted web crawling
- Docker
- multi-agent swarm
- arbitrary code execution
- unnecessary databases
- unnecessary frameworks

until the core system works reliably.

---

# 26. Expected Execution

A successful execution should look conceptually like:

```text
START
 ↓
Load Candidate
 ↓
Validate Candidate
 ↓
Generate Mission
 ↓
Load Memory
 ↓
OBSERVE
 ↓
DIAGNOSE
 ↓
DECIDE
 ↓
Generate Search Strategy
 ↓
Search LinkedIn through SearXNG
 ↓
Normalize
 ↓
Deduplicate
 ↓
Apply Hard Filters
 ↓
Evaluate Jobs
 ↓
Store Accepted Jobs
 ↓
Update Memory
 ↓
REFLECT
 ↓
Enough jobs?
 ├── YES → Save Results → STOP
 └── NO
       ↓
    Replan
       ↓
    Next Iteration
```

---

# 27. Final Architectural Principle

The most important rule of this project is:

> The LLM is the reasoning component. Python is the control component.

The LLM proposes.

Python validates.

Python executes.

Python records the result.

The Brain observes the result.

The Brain decides what should happen next.

This separation must remain intact throughout the project.

---

# 28. Instructions to Antigravity

When asked to implement this project:

- Read `AGENTS.md` completely before changing code.
- Inspect the repository before creating files.
- Follow the architecture defined here.
- Implement incrementally.
- Keep the code runnable after each phase.
- Do not invent a different architecture without explicit instruction.
- Do not give the LLM unrestricted filesystem or shell access.
- Do not introduce Docker.
- Do not replace Python orchestration with an LLM swarm.
- Do not skip the Brain feedback loop.
- Do not hardcode a fixed sequence of searches.
- Do not bypass the Sandbox.
- Do not expose `.env` or project source files to the agent.
- Do not change UI/design requirements unless explicitly requested.
- If an architectural conflict is found, stop and explain the conflict before making a large structural change.

The final implementation must remain faithful to this document.