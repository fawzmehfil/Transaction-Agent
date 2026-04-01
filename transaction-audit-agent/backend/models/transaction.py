"""
Pydantic models for transactions and audit results.
"""
from pydantic import BaseModel, field_validator
from typing import Optional, List
from datetime import date
from enum import Enum


class TransactionType(str, Enum):
    debit = "debit"
    credit = "credit"
    transfer = "transfer"
    refund = "refund"


class TransactionCategory(str, Enum):
    travel = "travel"
    meals = "meals"
    supplies = "supplies"
    software = "software"
    hardware = "hardware"
    consulting = "consulting"
    utilities = "utilities"
    marketing = "marketing"
    other = "other"
    unknown = "unknown"


class TransactionCreate(BaseModel):
    date: date
    merchant: str
    amount: float
    category: str
    type: str

    @field_validator("amount")
    @classmethod
    def amount_must_be_positive(cls, v):
        if v <= 0:
            raise ValueError("Amount must be greater than zero")
        return round(v, 2)

    @field_validator("merchant")
    @classmethod
    def merchant_must_not_be_empty(cls, v):
        if not v or not v.strip():
            raise ValueError("Merchant name cannot be empty")
        return v.strip()


class Transaction(BaseModel):
    id: int
    date: date
    merchant: str
    amount: float
    category: str
    type: str
    flags: List[str] = []

    class Config:
        from_attributes = True


class AuditSeverity(str, Enum):
    low = "low"
    medium = "medium"
    high = "high"


class AuditIssue(BaseModel):
    type: str
    severity: AuditSeverity
    description: str
    affected_transaction_ids: List[int]


class AuditResult(BaseModel):
    issues: List[AuditIssue]
    risk_score: float
    summary: dict


class ChatRequest(BaseModel):
    message: str
    conversation_history: Optional[List[dict]] = []


class ChatResponse(BaseModel):
    reply: str
    context_used: dict
