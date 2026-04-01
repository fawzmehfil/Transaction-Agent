"""
Audit Engine: rule-based anomaly detection for financial transactions.

Rules implemented:
  1. Duplicate transactions (same merchant + amount within 3 days)
  2. Large transactions (above configurable threshold)
  3. Rapid repeated transactions (same merchant, multiple in short window)
  4. Missing/invalid category
  5. Invalid amounts (zero or negative — caught at ingestion, but re-checked here)
"""
from datetime import date, timedelta
from collections import defaultdict
from typing import List, Dict, Any

# --- Configurable thresholds ---
LARGE_TRANSACTION_THRESHOLD = 5000.0   # flag amounts above this
RAPID_REPEAT_WINDOW_DAYS    = 3        # window to detect rapid repeats
RAPID_REPEAT_MIN_COUNT      = 3        # how many hits in that window is suspicious
DUPLICATE_WINDOW_DAYS       = 3        # days window for duplicate detection
KNOWN_CATEGORIES = {
    "travel", "meals", "supplies", "software",
    "hardware", "consulting", "utilities", "marketing", "other"
}

# Severity weights used to compute the overall risk score
SEVERITY_WEIGHT = {"low": 1, "medium": 3, "high": 10}


def run_audit(transactions: List[Dict[str, Any]]) -> Dict[str, Any]:
    """
    Run all audit rules against the transaction list.
    Returns a dict with issues, risk_score, and summary.
    """
    issues = []
    issues.extend(_detect_duplicates(transactions))
    issues.extend(_detect_large_transactions(transactions))
    issues.extend(_detect_rapid_repeats(transactions))
    issues.extend(_detect_category_issues(transactions))

    risk_score = _compute_risk_score(issues, len(transactions))

    summary = _build_summary(issues, transactions)

    return {
        "issues": issues,
        "risk_score": risk_score,
        "summary": summary,
    }


# ---------------------------------------------------------------------------
# Rule implementations
# ---------------------------------------------------------------------------

def _detect_duplicates(transactions: List[dict]) -> List[dict]:
    """Flag pairs of transactions with same merchant + amount within window."""
    issues = []
    n = len(transactions)
    flagged_pairs = set()

    for i in range(n):
        for j in range(i + 1, n):
            t1, t2 = transactions[i], transactions[j]
            if t1["merchant"].lower() != t2["merchant"].lower():
                continue
            if abs(t1["amount"] - t2["amount"]) > 0.01:
                continue
            d1 = _parse_date(t1["date"])
            d2 = _parse_date(t2["date"])
            if abs((d1 - d2).days) <= DUPLICATE_WINDOW_DAYS:
                pair_key = tuple(sorted([t1["id"], t2["id"]]))
                if pair_key not in flagged_pairs:
                    flagged_pairs.add(pair_key)
                    issues.append({
                        "type": "duplicate_transaction",
                        "severity": "high",
                        "description": (
                            f"Possible duplicate: {t1['merchant']} charged "
                            f"${t1['amount']:.2f} twice within {DUPLICATE_WINDOW_DAYS} days "
                            f"(IDs {t1['id']} and {t2['id']})."
                        ),
                        "affected_transaction_ids": list(pair_key),
                    })
    return issues


def _detect_large_transactions(transactions: List[dict]) -> List[dict]:
    """Flag transactions whose amount exceeds the large-transaction threshold."""
    issues = []
    for t in transactions:
        if t["amount"] > LARGE_TRANSACTION_THRESHOLD:
            issues.append({
                "type": "large_transaction",
                "severity": "medium",
                "description": (
                    f"Transaction ID {t['id']} from {t['merchant']} is unusually large "
                    f"(${t['amount']:.2f} > threshold ${LARGE_TRANSACTION_THRESHOLD:.2f})."
                ),
                "affected_transaction_ids": [t["id"]],
            })
    return issues


def _detect_rapid_repeats(transactions: List[dict]) -> List[dict]:
    """Flag merchants with RAPID_REPEAT_MIN_COUNT+ transactions in the repeat window."""
    issues = []
    # Group by merchant
    by_merchant: Dict[str, List[dict]] = defaultdict(list)
    for t in transactions:
        by_merchant[t["merchant"].lower()].append(t)

    for merchant, txns in by_merchant.items():
        if len(txns) < RAPID_REPEAT_MIN_COUNT:
            continue
        # Sort by date and use a sliding window
        txns_sorted = sorted(txns, key=lambda x: _parse_date(x["date"]))
        for i in range(len(txns_sorted)):
            window = [txns_sorted[i]]
            base_date = _parse_date(txns_sorted[i]["date"])
            for j in range(i + 1, len(txns_sorted)):
                if (_parse_date(txns_sorted[j]["date"]) - base_date).days <= RAPID_REPEAT_WINDOW_DAYS:
                    window.append(txns_sorted[j])
                else:
                    break
            if len(window) >= RAPID_REPEAT_MIN_COUNT:
                ids = [t["id"] for t in window]
                # Avoid reporting overlapping windows for same set
                issues.append({
                    "type": "rapid_repeat_transactions",
                    "severity": "medium",
                    "description": (
                        f"{len(window)} transactions to {txns_sorted[i]['merchant']} "
                        f"within {RAPID_REPEAT_WINDOW_DAYS} days "
                        f"(IDs: {', '.join(str(i) for i in ids)})."
                    ),
                    "affected_transaction_ids": ids,
                })
                break  # one alert per merchant is enough
    return issues


def _detect_category_issues(transactions: List[dict]) -> List[dict]:
    """Flag transactions with missing, blank, or unrecognized categories."""
    issues = []
    for t in transactions:
        cat = (t.get("category") or "").strip().lower()
        if not cat or cat == "unknown":
            issues.append({
                "type": "missing_category",
                "severity": "low",
                "description": (
                    f"Transaction ID {t['id']} ({t['merchant']}, ${t['amount']:.2f}) "
                    f"has a missing or unknown category."
                ),
                "affected_transaction_ids": [t["id"]],
            })
        elif cat not in KNOWN_CATEGORIES:
            issues.append({
                "type": "unrecognized_category",
                "severity": "low",
                "description": (
                    f"Transaction ID {t['id']} has unrecognized category '{t['category']}'."
                ),
                "affected_transaction_ids": [t["id"]],
            })
    return issues


# ---------------------------------------------------------------------------
# Risk scoring
# ---------------------------------------------------------------------------

def _compute_risk_score(issues: List[dict], total_transactions: int) -> float:
    """
    Risk score 0–100 based on severity-weighted issue count relative to dataset size.
    """
    if not issues or total_transactions == 0:
        return 0.0
    weighted_sum = sum(SEVERITY_WEIGHT.get(issue["severity"], 1) for issue in issues)
    # Normalize: max reasonable score anchored at 20 high-severity issues per 100 txns
    raw = weighted_sum / max(total_transactions, 1) * 100
    return round(min(raw * 5, 100), 1)


def _build_summary(issues: List[dict], transactions: List[dict]) -> dict:
    """Build a structured summary for the AI agent context."""
    severity_counts = {"high": 0, "medium": 0, "low": 0}
    type_counts: Dict[str, int] = defaultdict(int)
    flagged_ids: set = set()

    for issue in issues:
        severity_counts[issue["severity"]] = severity_counts.get(issue["severity"], 0) + 1
        type_counts[issue["type"]] += 1
        for tid in issue["affected_transaction_ids"]:
            flagged_ids.add(tid)

    # Category breakdown of flagged transactions
    flagged_by_category: Dict[str, int] = defaultdict(int)
    for t in transactions:
        if t["id"] in flagged_ids:
            flagged_by_category[t.get("category", "unknown")] += 1

    return {
        "total_transactions": len(transactions),
        "total_issues": len(issues),
        "severity_counts": severity_counts,
        "issue_type_counts": dict(type_counts),
        "flagged_transaction_count": len(flagged_ids),
        "flagged_by_category": dict(flagged_by_category),
        "top_issue_types": sorted(type_counts.items(), key=lambda x: -x[1])[:3],
    }


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _parse_date(date_str) -> date:
    """Parse a date string or date object into a date."""
    if isinstance(date_str, date):
        return date_str
    for fmt in ("%Y-%m-%d", "%m/%d/%Y", "%d-%m-%Y"):
        try:
            from datetime import datetime
            return datetime.strptime(str(date_str), fmt).date()
        except ValueError:
            continue
    raise ValueError(f"Cannot parse date: {date_str}")
