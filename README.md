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
├── storage/
│   ├── __init__.py
│   └── memory.py            # Persistent agent memory state
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
│   ├── input/               # Candidate input profiles (Read-only)
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

The agent operates strictly within an application-level sandbox:

| Directory | Permission | Purpose |
|---|---|---|
| `sandbox/input/` | Read | Candidate profiles |
| `sandbox/output/` | Read / Write | Accepted jobs output (`jobs.json`) |
| `sandbox/memory/` | Read / Write | Search history & stats (`agent_memory.json`) |
| `sandbox/logs/` | Append / Write | Execution log (`agent.log`) |
| `sandbox/workspace/` | Read / Write | Temporary processing |

Attempts to access project code, `.env`, `.git`, or the parent filesystem via `../` traversal or absolute paths are strictly blocked by `SandboxSecurityError`.

---

## 5. Prerequisites

Ensure local services are running on your machine:

1. **Ollama**:
   - Running at: `http://localhost:11434`
   - Recommended model: `llama3.1:8b` or `qwen3.5:9b`
2. **SearXNG**:
   - Running at: `http://localhost:8081` with JSON API enabled

---

## 6. Quick Start

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

### 3. Add Candidate Profile
Place your candidate profile in `sandbox/input/candidate.json`:
```json
{
  "target_roles": ["Python Developer", "Backend Engineer"],
  "skills": ["Python", "FastAPI", "Django", "PostgreSQL"],
  "experience_years": 3,
  "locations": ["Delhi", "Noida", "Gurgaon"],
  "work_modes": ["remote", "hybrid"],
  "target_job_count": 5
}
```

### 4. Run the Autonomous Brain
```bash
python main.py
```

### 5. Inspect Results
- Accepted jobs: `sandbox/output/jobs.json`
- Agent memory & history: `sandbox/memory/agent_memory.json`
- Logs: `sandbox/logs/agent.log`
