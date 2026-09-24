# 🖥️ Runtime Architecture

> [!IMPORTANT]
> The Job Hunter is designed as a **local-first autonomous system**.
>
> Runtime infrastructure should remain separate from agent reasoning and business logic.

---

# 🏗️ 1. Runtime Overview

```text
┌─────────────────────────────────────────┐
│              LOCAL MACHINE              │
│                                         │
│  ┌───────────────┐                      │
│  │ Candidate JSON│                      │
│  └───────┬───────┘                      │
│          │                              │
│          ▼                              │
│  ┌─────────────────────┐                │
│  │   Agentic Runtime   │                │
│  │                     │                │
│  │    Master Brain     │                │
│  │    Hunter           │                │
│  │    Auditor          │                │
│  │    Pipeline         │                │
│  └──────┬───────┬──────┘                │
│         │       │                       │
│         ▼       ▼                       │
│   ┌─────────┐ ┌─────────┐               │
│   │ Ollama  │ │ SearXNG │               │
│   │ :11434  │ │ :8081   │               │
│   └─────────┘ └─────────┘               │
│                                         │
│  ┌─────────────────────────────────┐    │
│  │ Worker / Server :8000           │    │
│  │ SSE Telemetry                   │    │
│  └─────────────────────────────────┘    │
│                                         │
└─────────────────────────────────────────┘
```

---

# 🧠 2. Local LLM

Ollama provides the local language model runtime.

Typical endpoint:

```text
http://localhost:11434
```

The LLM may assist with:

* semantic interpretation
* reasoning
* query strategy
* job evaluation
* Brain decisions

The LLM does not automatically gain permission to change architecture.

---

# 🔎 3. SearXNG

SearXNG provides search aggregation.

Typical endpoint:

```text
http://localhost:8081
```

Its responsibility is discovery.

Search results are treated as external/untrusted information.

---

# ⚙️ 4. Agent Runtime

The agent runtime coordinates:

* infrastructure checks
* candidate loading
* criteria creation
* Brain execution
* pipeline execution
* output generation
* metrics

---

# 🌐 5. Worker / Server

The worker server exposes runtime functionality and telemetry.

Typical endpoint:

```text
http://localhost:8000
```

Important runtime endpoints conceptually include:

```text
GET /api/health
GET /api/stream
```

---

# 📡 6. SSE Telemetry

The server may expose mission progress through Server-Sent Events.

Conceptual event flow:

```text
Mission Started
      ↓
Sentry
      ↓
Think
      ↓
Hunter
      ↓
Auditor
      ↓
Brain
      ↓
More Work / Completion
      ↓
stream_end
```

Telemetry describes execution.

It does not redefine architecture.

---

# 📂 7. Project Runtime Storage

Typical runtime locations:

```text
sandbox/
├── input/
│   └── candidate_sample.json
│
├── output/
│   └── agentic_jobs_*.json
│
└── logs/
    └── ...
```

### Input

Candidate profile and mission requirements.

### Output

Validated job results.

### Logs

Runtime diagnostics and mission telemetry.

---

# 🩺 8. Infrastructure Health

Before autonomous execution, required infrastructure should be verified.

Conceptually:

```text
Infrastructure Check
       │
       ├── Ollama
       ├── SearXNG
       ├── Runtime
       └── Required paths
```

If a required dependency is unavailable, the mission should report the infrastructure problem rather than producing misleading results.

---

# ⏱️ 9. Runtime Limits

Autonomous execution should respect configured limits such as:

* maximum iterations
* maximum runtime
* search limits
* retry limits

Limits prevent runaway autonomous execution.

---

# 🧾 10. Metrics

The runtime may track:

* execution time
* search queries
* URLs discovered
* pages processed
* rejected jobs
* valid jobs
* token usage
* local execution cost
* estimated savings

Metrics describe execution and should not change candidate requirements.

---

# 🔐 11. Local-First Principle

The system should prefer local infrastructure whenever possible.

```text
Candidate Data
      │
      ▼
Local Runtime
      │
      ├── Local LLM
      ├── Local Search
      ├── Local Processing
      └── Local Storage
```

External websites are used for job discovery/content retrieval where necessary.

---

# 🚨 12. Runtime Failure States

Runtime failures should be distinguishable.

| Failure                | Meaning                            |
| ---------------------- | ---------------------------------- |
| `INFRASTRUCTURE_ERROR` | Required service unavailable       |
| `SEARCH_ERROR`         | Search operation failed            |
| `PARSING_ERROR`        | Data could not be processed        |
| `TIMEOUT`              | Operation exceeded allowed time    |
| `MODEL_ERROR`          | Local LLM operation failed         |
| `OUTPUT_ERROR`         | Final output could not be produced |

A runtime failure must not automatically be interpreted as a candidate rejection.

---

# 🛡️ 13. Runtime vs Architecture

Runtime configuration can change without changing architecture.

For example:

```text
Model name
Port
Timeout
Iteration limit
Log level
```

However, changing:

```text
Brain responsibility
Agent boundaries
Data contracts
Pipeline stages
Runtime component responsibilities
```

is an architectural change.

---

# 🚨 14. Architecture Change Approval

If runtime implementation requires changing the established architecture:

> 🛑 **STOP.**

Follow:

```text
STOP
 ↓
Explain
 ↓
Identify affected architecture
 ↓
Propose smallest change
 ↓
Explain impact
 ↓
Ask user approval
 ↓
Wait
 ↓
Implement only after approval
```

---

# 🏁 Core Principle

> **Runtime executes the architecture.**
>
> **It must not silently redefine the architecture.**
