"""The demo company's operational database (contract 0.12.0): the one dataset behind `kairos_demo_data`.

`scripts/seed_demo_data.py` loads it into Postgres; `FakeToolExecutor` loads it into in-memory SQLite, so fake-mode
tests run the same SQL on the same rows. Amounts are rupees (1 lakh = 100,000). Consistent with the OKF bundle:
PayCo's SDK licence (3.0 lakh a year) plus the emergency SDK v5 support contract (1.8 lakh), CloudCo's committed
compute (9.0 lakh a year) and the Apollo dual-run cloud bills, Cumulus's warehouse (its 40% price rise starts in Q4).

Deliberately messy: void and pending invoices (only `paid` counts), invoices dated just outside Q3, odd amounts.
Vendors paid more than their Q3 2026 contract, by how much (EXPECTED_Q3_OVERPAID): PayCo 42,350.00, CloudCo
143,550.75, TalentX 11,280.00.
"""
from __future__ import annotations

import sqlite3
from typing import Any

Q3 = ("2026-07-01", "2026-09-30")

TABLES: dict[str, list[tuple[str, str, str]]] = {  # table -> [(column, SQL type, note for the schema prompt)]
    "vendors": [("vendor_id", "TEXT PRIMARY KEY", ""), ("name", "TEXT NOT NULL", ""), ("category", "TEXT", "")],
    "contracts": [("contract_id", "TEXT PRIMARY KEY", ""), ("vendor_id", "TEXT NOT NULL", "references vendors"),
                  ("quarter", "TEXT NOT NULL", "e.g. '2026-Q3'; one row per vendor and quarter"),
                  ("contract_value", "NUMERIC(12,2) NOT NULL", "rupees agreed for that quarter"),
                  ("description", "TEXT", "")],
    "invoices": [("invoice_id", "TEXT PRIMARY KEY", ""), ("vendor_id", "TEXT NOT NULL", "references vendors"),
                 ("project", "TEXT", "Apollo, Zeus, Hermes, ..."), ("invoice_date", "DATE NOT NULL", ""),
                 ("amount", "NUMERIC(12,2) NOT NULL", "rupees"),
                 ("status", "TEXT NOT NULL", "'paid' | 'pending' | 'void'; only 'paid' counts as paid")],
    "cloud_costs": [("month", "TEXT NOT NULL", "'YYYY-MM'"), ("project", "TEXT NOT NULL", ""),
                    ("provider", "TEXT NOT NULL", ""), ("amount", "NUMERIC(12,2) NOT NULL", "rupees")],
    "headcount": [("month", "TEXT NOT NULL", "'YYYY-MM'"), ("team", "TEXT NOT NULL", ""), ("project", "TEXT", ""),
                  ("fte", "NUMERIC(5,2) NOT NULL", "")],
    "tickets": [("ticket_key", "TEXT PRIMARY KEY", ""), ("project", "TEXT NOT NULL", ""), ("title", "TEXT NOT NULL", ""),
                ("status", "TEXT NOT NULL", ""), ("opened", "DATE NOT NULL", "")],
    "finance_notes": [("note_id", "TEXT PRIMARY KEY", ""), ("created_at", "TEXT NOT NULL", "ISO timestamp"),
                      ("author", "TEXT NOT NULL", ""), ("subject", "TEXT NOT NULL", ""), ("body", "TEXT NOT NULL", "")],
}

ROWS: dict[str, list[tuple[Any, ...]]] = {
    "vendors": [
        ("V-PAYCO", "PayCo", "payments SDK"), ("V-CLOUDCO", "CloudCo", "cloud"), ("V-CUMULUS", "Cumulus Data", "warehouse"),
        ("V-DESKLY", "Deskly", "helpdesk SaaS"), ("V-TALENTX", "TalentX", "contract engineers"),
        ("V-PRINTHUB", "PrintHub", "office supplies"),
    ],
    "contracts": [
        ("C-PAYCO-26Q3", "V-PAYCO", "2026-Q3", 255000.00, "SDK licence FY26 (Q3 share 75,000) + emergency SDK v5 support 1.8 lakh"),
        ("C-CLOUDCO-26Q3", "V-CLOUDCO", "2026-Q3", 225000.00, "Committed-use compute, 9.0 lakh a year"),
        ("C-CUMULUS-26Q3", "V-CUMULUS", "2026-Q3", 120000.00, "Warehouse compute credits (renewal price from 1 Nov)"),
        ("C-DESKLY-26Q3", "V-DESKLY", "2026-Q3", 30000.00, "Helpdesk seats"),
        ("C-TALENTX-26Q3", "V-TALENTX", "2026-Q3", 450000.00, "Two contract backend engineers"),
        ("C-PRINTHUB-26Q3", "V-PRINTHUB", "2026-Q3", 20000.00, "Office supplies"),
        ("C-PAYCO-26Q4", "V-PAYCO", "2026-Q4", 75000.00, "SDK licence FY26, Q4 share"),
    ],
    "invoices": [
        ("INV-7101", "V-PAYCO", "Apollo", "2026-07-05", 75000.00, "paid"),
        ("INV-7188", "V-PAYCO", "Apollo", "2026-08-04", 180000.00, "paid"),
        ("INV-7240", "V-PAYCO", "Apollo", "2026-09-12", 42350.00, "paid"),      # support hours beyond the emergency contract
        ("INV-7322", "V-PAYCO", "Apollo", "2026-10-02", 18750.00, "pending"),   # Q4
        ("INV-6990", "V-CLOUDCO", "Apollo", "2026-06-30", 51200.00, "paid"),    # Q2
        ("INV-7104", "V-CLOUDCO", "Apollo", "2026-07-31", 78400.00, "paid"),
        ("INV-7199", "V-CLOUDCO", "Apollo", "2026-08-31", 131250.75, "paid"),
        ("INV-7301", "V-CLOUDCO", "Apollo", "2026-09-30", 158900.00, "paid"),
        ("INV-7110", "V-CUMULUS", "Zeus", "2026-07-10", 40000.00, "paid"),
        ("INV-7205", "V-CUMULUS", "Zeus", "2026-08-10", 39800.00, "paid"),
        ("INV-7288", "V-CUMULUS", "Zeus", "2026-09-10", 40000.00, "paid"),
        ("INV-7115", "V-DESKLY", "Hermes", "2026-07-15", 30000.00, "paid"),
        ("INV-7116", "V-DESKLY", "Hermes", "2026-07-16", 12000.00, "void"),     # duplicate, voided
        ("INV-7120", "V-TALENTX", "Apollo", "2026-07-28", 153760.00, "paid"),
        ("INV-7212", "V-TALENTX", "Apollo", "2026-08-28", 153760.00, "paid"),
        ("INV-7295", "V-TALENTX", "Apollo", "2026-09-28", 153760.00, "paid"),
        ("INV-7296", "V-TALENTX", "Zeus", "2026-09-29", 55000.00, "pending"),
        ("INV-7130", "V-PRINTHUB", "Hermes", "2026-08-19", 18640.00, "paid"),
    ],
    "cloud_costs": [
        ("2026-07", "Apollo", "CloudCo", 60000.00), ("2026-07", "Zeus", "CloudCo", 12400.00), ("2026-07", "Hermes", "CloudCo", 6000.00),
        ("2026-08", "Apollo", "CloudCo", 110000.00), ("2026-08", "Zeus", "CloudCo", 14250.75), ("2026-08", "Hermes", "CloudCo", 7000.00),
        ("2026-09", "Apollo", "CloudCo", 140000.00), ("2026-09", "Zeus", "CloudCo", 12900.00), ("2026-09", "Hermes", "CloudCo", 6000.00),
    ],
    "headcount": [
        ("2026-09", "payments", "Apollo", 6.0), ("2026-09", "platform", "Apollo", 2.5), ("2026-09", "data", "Zeus", 3.0),
        ("2026-09", "support", "Hermes", 1.5), ("2026-09", "contract (TalentX)", "Apollo", 2.0),
    ],
    "tickets": [
        ("APOLLO-12", "Apollo", "Payments DB migration", "In Progress", "2026-06-02"),
        ("APOLLO-31", "Apollo", "Vendor SDK upgrade", "Blocked", "2026-07-08"),
        ("APOLLO-33", "Apollo", "PayCo certification", "Blocked", "2026-07-21"),
        ("ZEUS-9", "Zeus", "Per-team query budgets", "To Do", "2026-09-03"),
        ("ZEUS-11", "Zeus", "Q4 warehouse cost guardrails", "In Progress", "2026-09-10"),
    ],
    "finance_notes": [],
}

EXPECTED_Q3_OVERPAID = {"PayCo": 42350.00, "CloudCo": 143550.75, "TalentX": 11280.00}


def ddl(table: str) -> str:
    cols = ", ".join(f"{c} {t}" for c, t, _ in TABLES[table])
    return f"CREATE TABLE {table} ({cols})"


def schema_doc() -> dict[str, Any]:
    """What a data engineer is told about the database (the db.schema operation)."""
    return {"dialect": "PostgreSQL", "tables": [
        {"name": t, "columns": [{"name": c, "type": ty.split()[0], **({"note": n} if n else {})} for c, ty, n in cols]}
        for t, cols in TABLES.items()],
        "notes": ["Q3 2026 is invoice_date between '2026-07-01' and '2026-09-30'.",
                  "contracts has one row per vendor and quarter; join it on vendor_id and quarter = '2026-Q3'.",
                  "Only invoices with status = 'paid' count as paid.", "Amounts are rupees (1 lakh = 100,000)."]}


def sqlite_db() -> sqlite3.Connection:
    """The dataset in an in-memory SQLite database (the fake db tool)."""
    con = sqlite3.connect(":memory:", check_same_thread=False)
    for t in TABLES:
        con.execute(ddl(t))
        if ROWS[t]:
            con.executemany(f"INSERT INTO {t} VALUES ({', '.join('?' * len(ROWS[t][0]))})", ROWS[t])
    con.commit()
    return con


__all__ = ["EXPECTED_Q3_OVERPAID", "Q3", "ROWS", "TABLES", "ddl", "schema_doc", "sqlite_db"]
