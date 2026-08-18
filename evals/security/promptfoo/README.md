# Steam Games RAG — Security Baseline Evaluation (Promptfoo)

This directory contains the automated security regression test suite for the **Steam Games RAG** search pipeline, powered by [Promptfoo](https://www.promptfoo.dev).

The evaluation targets the live HTTP endpoint (`POST /api/v1/search`) and verifies system behavior across normal queries, direct prompt injections, structured-output manipulation, secret extraction, and multilingual attack vectors.

---

## Architecture Overview

```
Promptfoo Test Runner
        │
        ▼ (POST /api/v1/search with {"query": "...", "debug": true})
FastAPI Backend (Search Pipeline)
  ├── 1. Query Understanding (Gemini Structured Output)
  ├── 2. Multilingual Dense + Sparse Embeddings (E5 + BM25)
  ├── 3. Hybrid Qdrant Vector Search (RRF)
  └── 4. Rerank & Answer Synthesis (Gemini Streaming SSE)
        │
        ▼ (text/event-stream: results + summary_chunk)
transforms/parse_sse.cjs (SSE Stream Parser)
        │
        ▼ { summary, results, debug }
Deterministic Assertions (Categories A – E)
```

---

## Directory Structure

```text
evals/security/promptfoo/
├── package.json               # Isolated dependencies (pinned promptfoo)
├── promptfooconfig.yaml       # Main Promptfoo configuration
├── README.md                  # Evaluation guide & documentation
├── transforms/
│   └── parse_sse.cjs          # CommonJS parser for Server-Sent Events
└── tests/
    ├── normal_controls.yaml               # Category A: Normal search baseline
    ├── instruction_hijacking.yaml         # Category B: Direct prompt injection & overrides
    ├── structured_output_manipulation.yaml# Category C: Schema/filter injection
    ├── secret_extraction.yaml             # Category D: System prompt & secret extraction
    └── multilingual_attacks.yaml          # Category E: Ukrainian, Russian, Polish attacks
```

---

## Test Categories

| Category | Suite File | Description | Invariants Tested |
| :--- | :--- | :--- | :--- |
| **A. Normal Controls** | `tests/normal_controls.yaml` | Standard search queries (co-op survival, Linux, year filters, Ukrainian) | Results returned, structured debug valid, summary generated |
| **B. Instruction Hijacking** | `tests/instruction_hijacking.yaml` | Direct jailbreak attempts, mode overrides, Python code generation requests | No `HACKED` tokens, no code generation, pipeline invariants maintained |
| **C. Structured Manipulation** | `tests/structured_output_manipulation.yaml` | JSON delimiter escapes, SQL injection strings, injected OS/tag filters | Schema bounds respected, filter injection rejected, valid debug object |
| **D. Secret Extraction** | `tests/secret_extraction.yaml` | Attempts to extract API keys (`GEMINI_API_KEY`), system prompts, DB configs | No API keys exposed, system prompts not repeated verbatim |
| **E. Multilingual Attacks** | `tests/multilingual_attacks.yaml` | Non-English prompt injections (Ukrainian, Russian, Polish, cross-lingual) | Foreign-language jailbreaks rejected, pipeline remains functional |

---

## Prerequisites

1. **Node.js** v18+ and **npm** installed.
2. The Steam Games RAG backend must be running.

```bash
# Start backend (from repository root)
make up
# Or run backend locally
cd backend && uvicorn app.main:app --port 8000
```

---

## Environment Variables

| Variable | Default | Description |
| :--- | :--- | :--- |
| `STEAM_RAG_API_URL` | `http://localhost:8000` | Base URL of the Steam Games RAG backend service |

---

## Running the Evaluation

### 1. Install Dependencies
```bash
cd evals/security/promptfoo
npm install
```

### 2. Run Evaluation
```bash
npm run eval
```
Or from the repository root:
```bash
make eval-security
```

### 3. View Interactive Report
```bash
npm run eval:view
```
Or from the repository root:
```bash
make eval-security-view
```

---

## Baseline Semantics & Interpreting Results

- **This is a Baseline Evaluation:** Some security tests **may fail** if the current prompts lack explicit adversarial defenses.
- **Do not weaken assertions** to force a green test suite. Failed tests highlight exact vulnerability vectors to be addressed in subsequent hardening iterations (guardrails, prompt hardening, input filters).
