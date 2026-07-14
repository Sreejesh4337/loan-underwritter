"""Bank statement extraction.

One structured-output LLM call per document (never per transaction row,
consistent with the project's cost-minimization principle) that extracts the
account holder/type from the header block and every transaction row (date,
description, debit, credit, balance, category) from the table in one shot.
Requires OPENAI_API_KEY to be set in .env.
"""

from __future__ import annotations

import logging
from datetime import datetime

from pydantic import BaseModel, Field

from src.llm.models import CHEAP_MODEL_NAME, get_cheap_model
from src.llm.pricing import estimate_cost_usd
from src.parsers.bank_statement_parser import ParsedBankStatement
from src.schemas.underwriting import StepUsage, Transaction, TransactionCategory

logger = logging.getLogger(__name__)


class _TransactionItem(BaseModel):
    date: str = Field(description="ISO format YYYY-MM-DD")
    description: str
    debit: float = 0.0
    credit: float = 0.0
    balance: float
    category: str = Field(description="one of: salary, emi, return, cash_deposit, other")


class _BankStatementExtractionSchema(BaseModel):
    account_holder: str
    account_type: str
    transactions: list[_TransactionItem]


def extract_bank_statement(parsed: ParsedBankStatement) -> tuple[str | None, str | None, list[Transaction], StepUsage]:
    model = get_cheap_model().with_structured_output(_BankStatementExtractionSchema, include_raw=True)
    categories = ", ".join(c.value for c in TransactionCategory)
    prompt = (
        "Extract structured data from this bank statement.\n\n"
        "First, identify the account holder's name and account type (e.g. Savings/Current) "
        "from the header block.\n\n"
        "Then extract every transaction row from the table, in order: date (ISO format "
        "YYYY-MM-DD), description (verbatim), debit amount (0 if none), credit amount (0 if "
        "none), and the running balance after that transaction. Ignore any footer/disclaimer "
        "text that is not a transaction row.\n\n"
        f"For each transaction, also classify its description into exactly one of: {categories}. "
        'Use "salary" for salary/payroll credits, "emi" for loan EMI debits, "return" for '
        'bounced/returned/insufficient-funds transactions, "cash_deposit" for cash deposits, and '
        '"other" for anything else.\n\n'
        f"{parsed.raw_text}"
    )
    result = model.invoke(prompt)
    extraction: _BankStatementExtractionSchema = result["parsed"]
    raw_message = result["raw"]
    usage_meta = getattr(raw_message, "usage_metadata", None) or {}
    input_tokens = usage_meta.get("input_tokens", 0)
    output_tokens = usage_meta.get("output_tokens", 0)

    transactions = []
    for item in extraction.transactions:
        try:
            category = TransactionCategory(item.category.strip().lower())
        except ValueError:
            category = TransactionCategory.OTHER
        transactions.append(
            Transaction(
                txn_date=datetime.strptime(item.date.strip(), "%Y-%m-%d").date(),
                description=item.description,
                debit=item.debit,
                credit=item.credit,
                balance=item.balance,
                category=category,
            )
        )
    transactions.sort(key=lambda t: t.txn_date)

    usage = StepUsage(
        step="extract_bank_statement",
        model=CHEAP_MODEL_NAME,
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        cost_usd=estimate_cost_usd(CHEAP_MODEL_NAME, input_tokens, output_tokens),
    )
    return extraction.account_holder or None, extraction.account_type or None, transactions, usage
