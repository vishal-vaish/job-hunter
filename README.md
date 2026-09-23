# Autonomous Job Hunter

A local-first, Python-controlled autonomous job-hunting system powered by local LLMs (Ollama) and meta-search (SearXNG).

---

## 1. Project Overview

The Autonomous Job Hunter discovers, filters, and semantically evaluates relevant job opportunities for a candidate profile completely locally, without external cloud agent frameworks, without Docker, and without browser scraping.

### Core Philosophy

> **One Python-controlled Autonomous Brain + deterministic tools + local LLM.**

- **Python controls**: state, memory, iterations, tool execution, search dispatch, deduplication, hard filtering, sandbox security, and stopping conditions.
- **Local LLM is used selectively for**: candidate understanding, mission generation, search query adaptation, and semantic job evaluation.
- **The LLM never directly touches** the filesystem, network sockets, shell commands, or arbitrary Python execution.

---

## 2. System Flow

```text
User / Candidate Profile (sandbox/input/candidate.json)
        ↓
Profile Validation (ProfileValidator)
        ↓
Mission Generator (MissionGenerator)
        ↓
Autonomous Brain Feedback Loop:
  [OBSERVE]  → Inspect previous yield, duplicates, and rejection patterns
  [DIAGNOSE] → Detect query saturation, experience mismatch, or location friction
  [DECIDE]   → Adapt search query and keywords dynamically
  [ACT]      → Execute GlobalSearch → SearXNG → LinkedIn Provider
               Normalize → Deduplicate → Apply Hard Filters → LLM Evaluation
  [REFLECT]  → Persist memory state, evaluate quota, and iterate or stop
        ↓
Persist Final Accepted Jobs (sandbox/output/jobs.json)
```

---

## 3. Directory Structure

```text
job-hunter/
├── config/
│   ├── __init__.py
│   └── settings.py          # Centralized configuration & environment loader
├── models/
│   ├── __init__.py
│   ├── candidate.py         # CandidateProfile model
│   ├── mission.py           # SearchMission model
│   ├── job.py               # Normalized Job model
│   └── evaluation.py        # JobEvaluation model
├── security/
│   ├── __init__.py
│   └── sandbox.py           # Application-level filesystem sandbox
├── utils/
│   ├── __init__.py
│   └── logger.py            # Console & sandboxed file logging
├── infrastructure/
│   ├── __init__.py
│   ├── ollama.py            # Local Ollama client with structured JSON parsing
│   └── searxng.py           # Local SearXNG meta-search client
├── pipeline/
│   ├── __init__.py
│   ├── normalizer.py        # HTML and string sanitization
│   ├── deduplicator.py      # Canonical URL normalization and deduplication
│   └── filters.py           # Deterministic hard filters (companies, locations)
├── providers/
│   ├── __init__.py
│   ├── base.py              # BaseJobProvider abstract interface
│   └── linkedin.py          # Pluggable LinkedIn provider for SearXNG
├── search/
│   ├── __init__.py
│   └── global_search.py     # Provider router and discovery coordinator
├── data/
│   └── candidates/          # Source of truth candidate profiles (<customer_id>.json)
├── storage/
│   ├── __init__.py
│   ├── memory.py            # Persistent agent memory state
│   └── candidate_repository.py # CandidateRepository abstraction & local repository
├── agent/
│   ├── __init__.py
│   ├── profile_validator.py # Candidate profile validator
│   ├── mission_generator.py # Translates profile to SearchMission
│   ├── evaluator.py         # LLM semantic job matching against profile
│   ├── brain.py             # Autonomous Brain feedback loop orchestrator
│   └── tools/
│       ├── __init__.py
│       ├── search_jobs.py   # Narrow tool for GlobalSearch
│       ├── memory.py        # Narrow tool for sandbox/memory/ access
│       └── results.py       # Narrow tool for saving jobs to sandbox/output/
├── sandbox/
│   ├── output/              # Accepted jobs output (Read/Write)
│   ├── memory/              # Agent persistent memory (Read/Write)
│   ├── logs/                # System log files (Append/Write)
│   └── workspace/           # Temporary agent scratchpad (Read/Write)
├── main.py                  # CLI application entrypoint
├── requirements.txt         # Core dependencies
└── AGENTS.md                # System specification and design contracts
```

---

## 4. Sandbox Security Model

The agent operates strictly within an execution-focused sandbox:

| Directory | Permission | Purpose |
|---|---|---|
| `sandbox/output/` | Read / Write | Latest results (`jobs.json`) and run history (`runs/<run_id>/`) |
| `sandbox/memory/` | Read / Write | Persistent cross-run memory (`agent_memory.json`) |
| `sandbox/logs/` | Append / Write | Per-run log files (`<run_id>.log`) and aggregate `agent.log` |
| `sandbox/workspace/` | Read / Write | Temporary processing |

Attempts to access project code, `.env`, `.git`, or the parent filesystem via `../` traversal or absolute paths are strictly blocked by `SandboxSecurityError`. Candidate source data lives outside `sandbox/` in `data/candidates/`.

---

## 5. Prerequisites

Ensure local services are running on your machine:

1. **Ollama**:
   - Running at: `http://localhost:11434`
   - Recommended model: `llama3.1:8b` or `qwen3.5:9b`
2. **SearXNG**:
   - Running at: `http://localhost:8081` with JSON API enabled

---

## 6. Quick Start & CLI Execution Modes

### 1. Install Dependencies
```bash
pip install -r requirements.txt
```

### 2. Configure Environment (Optional)
Copy `.env.example` to `.env` if custom endpoints or models are desired:
```ini
OLLAMA_BASE_URL=http://localhost:11434
OLLAMA_MODEL=llama3.1:8b
SEARXNG_BASE_URL=http://localhost:8081
```

### 3. Candidate Profiles (data/candidates/<customer_id>.json)
Candidate source data is keyed by `customer_id`. Example `data/candidates/12345.json`:
```json
{
  "customer_id": "12345",
  "target_roles": ["Python Developer", "Backend Engineer"],
  "skills": ["Python", "FastAPI", "Django", "PostgreSQL"],
  "experience_years": 3,
  "locations": ["Delhi", "Noida", "Gurgaon"],
  "work_modes": ["remote", "hybrid"],
  "max_posting_age_days": 7,
  "target_job_count": 5
}
```

### 4. Running the Job Hunter

#### Mode 1: Interactive Prompt Mode (Customer-Independent)
```bash
python main.py
```
Prompts directly for the search request (e.g. `What kind of jobs are you looking for?`). If any key detail is missing (such as location or role), it asks follow-up clarifying questions (e.g. `Location not specified. Enter target location (or press Enter for 'Remote'):`), then executes the search and exits cleanly.

#### Mode 2: Registered Customer ID Mode (Direct / Headless)
```bash
python main.py --customer-id=12345
```
Directly loads candidate `12345` via `CandidateRepository` and executes immediately with **zero terminal prompts**.

#### Mode 3: Direct Search Prompt Mode (Non-interactive)
```bash
python main.py --prompt="Find React developer jobs in Bangalore posted in the last 7 days"
```
Synthesizes a candidate profile directly from the search prompt and executes the search.


*(Note: `--customer-id` and `--prompt` are mutually exclusive on the command line).*

### 5. Inspect Results & Execution History
Each execution generates a unique `run_id` (e.g. `run_YYYYMMDD_HHMMSS_<hex>`):
- **Current Output**:
  - `sandbox/output/jobs.json`: Discovered & accepted jobs from the latest completed run (sorted newest-first).
- **Historical Output**:
  - `sandbox/output/runs/<run_id>/jobs.json`: Snapshot of accepted jobs for that specific run.
  - `sandbox/output/runs/<run_id>/summary.json`: Deterministic execution counters and rejection reasons with associated `customer_id` and `search_prompt`.
  - `sandbox/output/runs/<run_id>/run.json`: Run lifecycle metadata, `customer_id`, `search_prompt`, and status (`completed` or `failed`).
- **Logs**:
  - `sandbox/logs/<run_id>.log`: Isolated, detailed execution trace for each specific run.
- **Cross-Run Persistent Memory**:
  - `sandbox/memory/agent_memory.json`: Cumulative searched queries and lifetime search statistics.


