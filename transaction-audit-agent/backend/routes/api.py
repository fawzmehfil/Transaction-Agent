"""
FastAPI route definitions.
"""
import json
from fastapi import APIRouter, HTTPException, UploadFile, File
from fastapi.responses import JSONResponse
from typing import List

from backend.models.transaction import TransactionCreate, ChatRequest
from backend.services import transaction_service as ts
from backend.services import agent_service as ag

router = APIRouter()


# ---------------------------------------------------------------------------
# Transaction endpoints
# ---------------------------------------------------------------------------

@router.post("/upload-transactions")
async def upload_transactions(file: UploadFile = File(...)):
    """Accept a CSV file and ingest valid transactions."""
    if not file.filename.endswith(".csv"):
        raise HTTPException(status_code=400, detail="Only CSV files are accepted.")

    content = await file.read()
    inserted, errors = ts.ingest_csv(content)

    # Re-run audit after ingestion so flags are fresh
    if inserted > 0:
        ts.compute_and_store_audit()

    return {
        "inserted": inserted,
        "errors": errors,
        "message": f"Inserted {inserted} transaction(s). {len(errors)} error(s).",
    }


@router.post("/transactions")
def create_transaction(tx: TransactionCreate):
    """Manually create a single transaction."""
    try:
        new_id = ts.insert_transaction(tx.model_dump())
        # Re-run audit
        ts.compute_and_store_audit()
        return {"id": new_id, "message": "Transaction created and audit refreshed."}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/transactions")
def get_transactions():
    """Return all transactions."""
    return ts.get_all_transactions()


@router.delete("/transactions")
def clear_transactions():
    """Delete all transactions (for testing/reset)."""
    ts.delete_all_transactions()
    return {"message": "All transactions deleted."}


# ---------------------------------------------------------------------------
# Audit endpoints
# ---------------------------------------------------------------------------

@router.get("/audit-results")
def get_audit_results():
    """Run (or refresh) the audit and return full results."""
    transactions = ts.get_all_transactions()
    if not transactions:
        return {"issues": [], "risk_score": 0, "summary": {}}
    result = ts.compute_and_store_audit()
    return result


@router.get("/risk-score")
def get_risk_score():
    """Return just the current risk score."""
    transactions = ts.get_all_transactions()
    if not transactions:
        return {"risk_score": 0}
    from backend.services.audit_engine import run_audit
    result = run_audit(transactions)
    return {"risk_score": result["risk_score"]}


# ---------------------------------------------------------------------------
# Agent endpoints
# ---------------------------------------------------------------------------

@router.post("/agent-chat")
def agent_chat(req: ChatRequest):
    """Chat with the audit AI agent."""
    transactions = ts.get_all_transactions()
    if not transactions:
        return {
            "reply": "No transactions loaded yet. Please upload a CSV or add transactions first.",
            "context_used": {},
        }

    from backend.services.audit_engine import run_audit
    audit_result = run_audit(transactions)

    result = ag.agent_chat(
        user_message=req.message,
        conversation_history=req.conversation_history or [],
        transactions=transactions,
        audit_result=audit_result,
    )
    return result


@router.get("/recommendations")
def get_recommendations():
    """Return rule-based action recommendations."""
    transactions = ts.get_all_transactions()
    if not transactions:
        return {"recommendations": []}

    from backend.services.audit_engine import run_audit
    audit_result = run_audit(transactions)
    recs = ag.generate_recommendations(audit_result)
    return {"recommendations": recs}
