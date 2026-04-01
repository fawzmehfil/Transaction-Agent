# Transaction Audit Agent

An AI-powered internal financial audit system that ingests transaction data, runs rule-based anomaly detection, and provides an interactive AI agent for explaining findings, prioritizing risks, and recommending actions.

---

## Architecture Overview

```
transaction-audit-agent/
├── main.py                          # FastAPI app entry point, serves frontend + mounts /api
├── requirements.txt
├── data/
│   └── sample_transactions.csv      # 50-row dataset with intentional anomalies
├── frontend/
│   └── index.html                   # Single-page app (HTML/CSS/JS + Chart.js)
└── backend/
    ├── models/
    │   └── transaction.py           # Pydantic models (TransactionCreate, AuditIssue, etc.)
    ├── routes/
    │   └── api.py                   # All FastAPI route handlers
    ├── services/
    │   ├── audit_engine.py          # Rule-based anomaly detection (pure Python)
    │   ├── transaction_service.py   # CRUD + CSV ingestion + flag persistence
    │   └── agent_service.py        # Context builder + Anthropic API integration
    └── utils/
        └── database.py             # SQLite connection, init, and row helpers
```

### How It Works

1. **Ingestion** → Transactions land in SQLite via CSV upload or manual entry
2. **Audit Engine** → 4 rule categories scan every transaction and emit structured issues
3. **Flag Persistence** → Each transaction row stores its flags as a JSON array
4. **Risk Scoring** → Severity-weighted formula produces a 0–100 score
5. **Agent** → Structured summary (not raw rows) is injected into the Claude prompt; responses are grounded in actual findings
6. **Frontend** → Single-page app with sidebar navigation, charts, issue list, chat UI

---

## Setup Instructions

### Prerequisites

- Python 3.10+
- pip

### 1. Clone and install

```bash
cd transaction-audit-agent
pip install -r requirements.txt
```

### 2. Set your Anthropic API key (optional but recommended)

```bash
export ANTHROPIC_API_KEY=sk-ant-...
```

The app runs fully without the API key — the audit engine, dashboard, and recommendations all work. Only the AI chat responses require the key (you get a fallback message otherwise).

### 3. Start the server

```bash
uvicorn main:app --reload --port 8000
```

### 4. Open the app

Visit: [http://localhost:8000](http://localhost:8000)

### 5. Load sample data

Go to **Import Data** → upload `data/sample_transactions.csv`

The sample file contains 50 transactions with intentional anomalies:
- Duplicate charges (Zoom, Uber Eats, Apple, Atlassian, Unknown Vendor)
- Large transactions above $5,000 threshold (Acme Consulting $12,500, Marriott $8,900, HP Inc $11,000)
- Rapid repeats (DoorDash 3× in 1 day, Starbucks 3× in 5 days)
- Missing categories (Stripe, Mystery Corp)
- Unrecognized categories (Unknown Vendor)

---

## API Reference

| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/api/upload-transactions` | Upload a CSV file |
| POST | `/api/transactions` | Create a single transaction |
| GET  | `/api/transactions` | List all transactions |
| DELETE | `/api/transactions` | Clear all transactions |
| GET  | `/api/audit-results` | Full audit report (issues + risk score + summary) |
| GET  | `/api/risk-score` | Just the risk score |
| POST | `/api/agent-chat` | Chat with the AI audit agent |
| GET  | `/api/recommendations` | Rule-based action recommendations |

---

## Audit Rules

| Rule | Severity | Logic |
|------|----------|-------|
| Duplicate Transaction | High | Same merchant + same amount within 3 days |
| Large Transaction | Medium | Amount > $5,000 (configurable in `audit_engine.py`) |
| Rapid Repeat | Medium | 3+ transactions to same merchant within 3 days |
| Missing Category | Low | Category is blank, null, or "unknown" |
| Unrecognized Category | Low | Category not in the known set |

Thresholds are defined as constants at the top of `backend/services/audit_engine.py` — easy to tune.

---

## Risk Score Formula

```
weighted_sum = Σ severity_weight[issue.severity]   # high=10, medium=3, low=1
raw = (weighted_sum / total_transactions) × 100
risk_score = min(raw × 5, 100)
```

---

## AI Agent Design

The agent is designed to be **grounded, not hallucinating**:

1. The audit engine produces a structured summary (counts, flagged IDs, top issues)
2. `agent_service.build_agent_context()` distills this into a compact JSON payload
3. That payload is injected into the user prompt — the LLM sees structured data, not raw SQL rows
4. The system prompt instructs the model to reference only facts present in the context

This means responses like *"Transaction #22 from Unknown Vendor was flagged for both duplicate_transaction and unrecognized_category"* are accurate and grounded.

---

## How to Present This in an Interview

### The One-Sentence Pitch
*"An internal audit tool that uses rule-based detection to flag financial anomalies and an AI agent that explains findings in plain language — the engine and the AI are deliberately separated so neither can bluff."*

### Key Design Decisions to Highlight

**1. Separation of concerns between rules and AI**
The audit engine is pure Python with no LLM involvement. The AI only explains findings — it can't invent them. This is the most important architectural decision. Say: *"I deliberately kept the rule engine deterministic. The AI adds explanation and prioritization on top, but every claim it makes is grounded in structured data I computed first."*

**2. Context injection, not raw data**
Instead of dumping 50 rows into a prompt, `build_agent_context()` computes a compact summary. Say: *"Sending raw rows wastes tokens and creates hallucination risk. I pre-aggregate into a structured summary the model can reason about reliably."*

**3. Pydantic for validation**
Mention that `TransactionCreate` catches bad data at the API boundary — negative amounts, empty merchants — before they pollute the database.

**4. Flag persistence**
Flags are re-computed and stored after every ingestion. Say: *"This lets the frontend query flagged transactions with a simple SQL filter rather than running the audit engine on every page load."*

**5. Configurable thresholds**
The `LARGE_TRANSACTION_THRESHOLD` and window sizes are named constants at the top of the engine module — easy to expose as config later.

### Potential Follow-up Questions & Answers

- **"How would you scale this?"** → Replace SQLite with Postgres, move audit to a background job queue (Celery/RQ), cache audit results in Redis.
- **"How would you test the audit engine?"** → Unit test each rule with hand-crafted fixture data; parametrize edge cases like boundary dates and exact-threshold amounts.
- **"Why not use a pre-trained fraud detection model?"** → Rule-based systems are auditable, explainable, and don't require labeled data. ML could complement, not replace, the rules layer.
- **"How do you prevent prompt injection via merchant names?"** → The context is injected as structured JSON, not free text interpolation. Merchant names are in a data field, not treated as instructions.

---

## Configuration

Edit constants in `backend/services/audit_engine.py`:

```python
LARGE_TRANSACTION_THRESHOLD = 5000.0   # dollar threshold for large-tx flag
RAPID_REPEAT_WINDOW_DAYS    = 3        # window in days for repeat detection
RAPID_REPEAT_MIN_COUNT      = 3        # how many hits trigger the flag
DUPLICATE_WINDOW_DAYS       = 3        # window for duplicate detection
```
