"""
Transaction service: handles ingestion, storage, and retrieval.
"""
import csv
import io
import json
from typing import List, Dict, Any, Tuple
from datetime import date

from backend.utils.database import get_connection, row_to_dict
from backend.services.audit_engine import run_audit

VALID_TYPES = {"debit", "credit", "transfer", "refund"}
KNOWN_CATEGORIES = {
    "travel", "meals", "supplies", "software",
    "hardware", "consulting", "utilities", "marketing", "other", "unknown"
}


def insert_transaction(tx: dict) -> int:
    """Insert a single transaction and return its new ID."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute(
        """
        INSERT INTO transactions (date, merchant, amount, category, type, flags)
        VALUES (?, ?, ?, ?, ?, ?)
        """,
        (
            str(tx["date"]),
            tx["merchant"].strip(),
            float(tx["amount"]),
            _normalize_category(tx.get("category", "unknown")),
            _normalize_type(tx.get("type", "debit")),
            "[]",
        ),
    )
    new_id = cursor.lastrowid
    conn.commit()
    conn.close()
    return new_id


def get_all_transactions() -> List[Dict[str, Any]]:
    """Return all transactions as a list of dicts."""
    conn = get_connection()
    rows = conn.execute("SELECT * FROM transactions ORDER BY date DESC").fetchall()
    conn.close()
    return [row_to_dict(r) for r in rows]


def get_transaction_by_id(tx_id: int) -> Dict[str, Any] | None:
    conn = get_connection()
    row = conn.execute("SELECT * FROM transactions WHERE id = ?", (tx_id,)).fetchone()
    conn.close()
    return row_to_dict(row) if row else None


def delete_all_transactions():
    """Clear all transactions (used for test resets)."""
    conn = get_connection()
    conn.execute("DELETE FROM transactions")
    conn.commit()
    conn.close()


def ingest_csv(content: bytes) -> Tuple[int, List[str]]:
    """
    Parse a CSV file and insert valid rows.
    Returns (inserted_count, list_of_error_messages).
    """
    text = content.decode("utf-8", errors="replace")
    reader = csv.DictReader(io.StringIO(text))
    inserted = 0
    errors = []

    required_fields = {"date", "merchant", "amount", "category", "type"}

    for row_num, row in enumerate(reader, start=2):  # row 1 is header
        # Normalize keys
        row = {k.strip().lower(): v.strip() for k, v in row.items() if k}

        missing = required_fields - set(row.keys())
        if missing:
            errors.append(f"Row {row_num}: missing fields {missing}")
            continue

        try:
            amount = float(row["amount"])
            if amount <= 0:
                errors.append(f"Row {row_num}: amount must be > 0 (got {row['amount']})")
                continue
        except ValueError:
            errors.append(f"Row {row_num}: invalid amount '{row['amount']}'")
            continue

        try:
            _parse_date(row["date"])
        except ValueError:
            errors.append(f"Row {row_num}: invalid date '{row['date']}'")
            continue

        if not row["merchant"]:
            errors.append(f"Row {row_num}: merchant cannot be empty")
            continue

        try:
            insert_transaction({
                "date": row["date"],
                "merchant": row["merchant"],
                "amount": amount,
                "category": row.get("category", "unknown"),
                "type": row.get("type", "debit"),
            })
            inserted += 1
        except Exception as e:
            errors.append(f"Row {row_num}: unexpected error — {e}")

    return inserted, errors


def update_transaction_flags(tx_id: int, flags: List[str]):
    """Update the flags column for a transaction."""
    conn = get_connection()
    conn.execute(
        "UPDATE transactions SET flags = ? WHERE id = ?",
        (json.dumps(flags), tx_id),
    )
    conn.commit()
    conn.close()


def compute_and_store_audit() -> dict:
    """Run the audit engine and persist flags back to each transaction."""
    transactions = get_all_transactions()
    result = run_audit(transactions)

    # Build a map: transaction_id -> list of issue type strings
    flag_map: Dict[int, List[str]] = {}
    for issue in result["issues"]:
        for tid in issue["affected_transaction_ids"]:
            flag_map.setdefault(tid, [])
            if issue["type"] not in flag_map[tid]:
                flag_map[tid].append(issue["type"])

    # Clear existing flags first
    conn = get_connection()
    conn.execute("UPDATE transactions SET flags = '[]'")
    conn.commit()
    conn.close()

    # Write new flags
    for tid, flags in flag_map.items():
        update_transaction_flags(tid, flags)

    return result


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _normalize_category(cat: str) -> str:
    cat = (cat or "").strip().lower()
    return cat if cat in KNOWN_CATEGORIES else "unknown"


def _normalize_type(t: str) -> str:
    t = (t or "").strip().lower()
    return t if t in VALID_TYPES else "debit"


def _parse_date(date_str: str) -> date:
    from datetime import datetime
    for fmt in ("%Y-%m-%d", "%m/%d/%Y", "%d-%m-%Y"):
        try:
            return datetime.strptime(date_str, fmt).date()
        except ValueError:
            continue
    raise ValueError(f"Cannot parse date: {date_str}")
