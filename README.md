# Transaction Audit Agent

An AI-powered financial audit system that detects transaction anomalies using rule-based logic and generates grounded, explainable insights through an integrated AI agent.

---

## Overview

This project simulates an internal audit tool that:

- Ingests transaction data (CSV or manual input)
- Detects anomalies using deterministic, rule-based logic
- Computes a risk score based on issue severity
- Uses an AI agent to explain findings and recommend actions

The system is designed with a strict separation between **audit logic (deterministic)** and **AI reasoning (explanatory)** to ensure reliability and prevent hallucinations.

---

## Tech Stack

- **Backend:** FastAPI, Python
- **Frontend:** HTML/CSS/JS (SPA), Chart.js
- **Database:** SQLite
- **Validation:** Pydantic
- **AI Integration:** Anthropic API (optional)

---

## How It Works

1. **Data Ingestion**  
   Upload CSV or manually add transactions → stored in SQLite

2. **Audit Engine**  
   Rule-based system scans transactions and flags anomalies

3. **Flag Persistence**  
   Flags are stored per transaction for efficient querying

4. **Risk Scoring**  
   Severity-weighted formula produces a score from 0–100

5. **AI Agent**  
   Uses structured audit summaries (not raw data) to explain findings

6. **Frontend Dashboard**  
   Displays charts, flagged issues, and an interactive chat interface

---

## Audit Rules

| Rule | Severity | Description |
|------|----------|-------------|
| Duplicate Transaction | High | Same merchant + amount within 3 days |
| Large Transaction | Medium | Amount > $5,000 |
| Rapid Repeat | Medium | 3+ transactions within 3 days |
| Missing Category | Low | Category is empty or unknown |
| Unrecognized Category | Low | Category not in predefined set |

---

## Risk Scoring

weighted_sum = Σ severity_weight
raw = (weighted_sum / total_transactions) × 100
risk_score = min(raw × 5, 100)


---

## AI Design (Key Highlight)

The AI agent is **grounded and constrained**:

- Uses **structured summaries**, not raw transaction data
- Receives **precomputed audit results**
- Is explicitly instructed to **only reference known facts**

This ensures:
- No hallucinated insights
- Fully explainable outputs
- Clear separation of responsibilities

---

## Setup

### Requirements
- Python 3.10+

### Install & Run

```bash
pip install -r requirements.txt
uvicorn main:app --reload --port 8000
