"""
Agent service: builds structured audit context and calls the Anthropic API
to produce grounded, context-aware responses.

Design principle: never send raw transaction rows to the model.
Instead, compute a compact structured summary and pass that.
"""
import os
import json
from typing import List, Dict, Any

import anthropic

_client = None


def _get_client() -> anthropic.Anthropic:
    global _client
    if _client is None:
        _client = anthropic.Anthropic()  # reads ANTHROPIC_API_KEY from env
    return _client


# ---------------------------------------------------------------------------
# Context builder — this is what gets sent to the LLM
# ---------------------------------------------------------------------------

def build_agent_context(transactions: List[dict], audit_result: dict) -> dict:
    """
    Distill the full audit result into a compact context object
    suitable for injection into an LLM prompt.
    """
    summary = audit_result.get("summary", {})
    issues = audit_result.get("issues", [])
    risk_score = audit_result.get("risk_score", 0)

    # Top 10 flagged transactions (by severity of their flags)
    flagged_ids = set()
    for issue in issues:
        for tid in issue["affected_transaction_ids"]:
            flagged_ids.add(tid)

    flagged_txns = [t for t in transactions if t["id"] in flagged_ids][:10]

    # Condense issues to avoid token bloat
    condensed_issues = [
        {
            "type": i["type"],
            "severity": i["severity"],
            "description": i["description"],
            "affected_count": len(i["affected_transaction_ids"]),
        }
        for i in issues
    ]

    return {
        "risk_score": risk_score,
        "summary": summary,
        "top_issues": condensed_issues[:15],  # cap to avoid prompt bloat
        "sample_flagged_transactions": [
            {
                "id": t["id"],
                "date": str(t["date"]),
                "merchant": t["merchant"],
                "amount": t["amount"],
                "category": t["category"],
                "flags": t.get("flags", []),
            }
            for t in flagged_txns
        ],
    }


# ---------------------------------------------------------------------------
# System prompt
# ---------------------------------------------------------------------------

SYSTEM_PROMPT = """You are an expert internal financial auditor AI assistant. 
You have been given a structured audit report for a set of financial transactions.

Your job is to:
- Answer user questions about the audit findings clearly and concisely
- Reference specific transaction IDs, merchants, and amounts when relevant
- Prioritize risk items from highest to lowest severity
- Suggest concrete, actionable next steps
- Keep responses professional, direct, and grounded in the data provided

You MUST only reference facts present in the audit context. Do not invent transactions or issues.
If asked about something not covered by the data, say so clearly.
"""


def build_user_prompt(user_message: str, context: dict) -> str:
    """Inject the audit context into the user message."""
    context_json = json.dumps(context, indent=2, default=str)
    return f"""AUDIT CONTEXT:
{context_json}

USER QUESTION:
{user_message}"""


# ---------------------------------------------------------------------------
# Chat handler
# ---------------------------------------------------------------------------

def agent_chat(
    user_message: str,
    conversation_history: List[dict],
    transactions: List[dict],
    audit_result: dict,
) -> Dict[str, Any]:
    """
    Run a chat turn with the audit agent.
    Returns {"reply": str, "context_used": dict}.
    """
    context = build_agent_context(transactions, audit_result)

    # Build messages: inject context into the first user turn
    messages = list(conversation_history)  # copy

    # For the current turn, enrich with context
    enriched_message = build_user_prompt(user_message, context)
    messages.append({"role": "user", "content": enriched_message})

    try:
        client = _get_client()
        response = client.messages.create(
            model="claude-sonnet-4-20250514",
            max_tokens=1024,
            system=SYSTEM_PROMPT,
            messages=messages,
        )
        reply = response.content[0].text
    except anthropic.AuthenticationError:
        reply = (
            "⚠️ No Anthropic API key configured. "
            "Set the ANTHROPIC_API_KEY environment variable to enable AI responses.\n\n"
            f"**Audit snapshot (from rule engine):**\n"
            f"- Risk score: {context['risk_score']}/100\n"
            f"- Total issues: {context['summary'].get('total_issues', 0)}\n"
            f"- High severity: {context['summary'].get('severity_counts', {}).get('high', 0)}\n"
            f"- Flagged transactions: {context['summary'].get('flagged_transaction_count', 0)}"
        )
    except Exception as e:
        reply = f"Agent error: {str(e)}"

    return {"reply": reply, "context_used": context}


# ---------------------------------------------------------------------------
# Action recommendations (rule-based, no LLM needed)
# ---------------------------------------------------------------------------

def generate_recommendations(audit_result: dict) -> List[dict]:
    """
    Generate a ranked list of recommended actions based on audit findings.
    This is deterministic and doesn't require the LLM.
    """
    issues = audit_result.get("issues", [])
    type_counts: Dict[str, int] = {}
    for issue in issues:
        type_counts[issue["type"]] = type_counts.get(issue["type"], 0) + 1

    recommendations = []

    if type_counts.get("duplicate_transaction", 0) > 0:
        recommendations.append({
            "priority": 1,
            "action": "Investigate Duplicate Transactions",
            "detail": (
                f"{type_counts['duplicate_transaction']} potential duplicate(s) found. "
                "Cross-reference with bank statements and contact the relevant vendors to confirm "
                "whether these are legitimate separate charges or billing errors."
            ),
            "severity": "high",
        })

    if type_counts.get("large_transaction", 0) > 0:
        recommendations.append({
            "priority": 2,
            "action": "Review High-Value Transactions",
            "detail": (
                f"{type_counts['large_transaction']} transaction(s) exceed the large-amount threshold. "
                "Verify approvals, check purchase orders, and confirm they comply with spending policy."
            ),
            "severity": "medium",
        })

    if type_counts.get("rapid_repeat_transactions", 0) > 0:
        recommendations.append({
            "priority": 3,
            "action": "Audit Rapid Repeat Merchant Charges",
            "detail": (
                f"{type_counts['rapid_repeat_transactions']} merchant(s) show repeated charges in a short window. "
                "Check for subscription double-billing, unauthorized purchases, or potential fraud."
            ),
            "severity": "medium",
        })

    if type_counts.get("missing_category", 0) + type_counts.get("unrecognized_category", 0) > 0:
        total = type_counts.get("missing_category", 0) + type_counts.get("unrecognized_category", 0)
        recommendations.append({
            "priority": 4,
            "action": "Resolve Missing or Inconsistent Categories",
            "detail": (
                f"{total} transaction(s) have missing or unrecognized categories. "
                "Correct categorization is essential for accurate financial reporting and policy compliance."
            ),
            "severity": "low",
        })

    if not recommendations:
        recommendations.append({
            "priority": 1,
            "action": "No Immediate Actions Required",
            "detail": "The audit engine found no policy violations. Continue monitoring regularly.",
            "severity": "low",
        })

    return recommendations
