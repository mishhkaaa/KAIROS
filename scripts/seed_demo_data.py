"""Create and fill `kairos_demo_data`, the demo company's operational database behind the db tool (P4, contract 0.12.0).

    uv run python scripts/seed_demo_data.py [--url postgresql+psycopg://kairos:kairos@127.0.0.1:5433/kairos_demo_data]

Idempotent: creates the database if it is missing, then drops and recreates its seven tables (vendors, contracts,
invoices, cloud_costs, headcount, tickets, finance_notes) from kairos_contracts.testing.demo_data. It only ever touches a
database named kairos_demo_data. The URL comes from --url, else KAIROS_DEMO_DATA_URL, else KAIROS_DATABASE_URL's server
with the database name swapped (so a machine whose Postgres is on another port does not seed the wrong server).
"""
from __future__ import annotations

import argparse
import os
import sys
from urllib.parse import urlsplit, urlunsplit

from kairos_contracts.testing import demo_data
from kairos_contracts.wiring import Settings

DB = "kairos_demo_data"


def target_url(explicit: str | None) -> str:
    if explicit:
        return explicit
    Settings.from_env()  # loads .env into the environment
    if os.getenv("KAIROS_DEMO_DATA_URL"):
        return os.environ["KAIROS_DEMO_DATA_URL"]
    base = urlsplit(os.getenv("KAIROS_DATABASE_URL", Settings().database_url))
    return urlunsplit(base._replace(path=f"/{DB}"))


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--url")
    url = target_url(ap.parse_args().url).replace("postgresql+psycopg://", "postgresql://", 1)
    parts = urlsplit(url)
    if parts.path.strip("/") != DB:
        print(f"refusing: the target database is {parts.path.strip('/')!r}, not {DB!r}", file=sys.stderr)
        return 2
    import psycopg

    print(f"seeding {DB} on {parts.hostname}:{parts.port or 5432}")
    admin = urlunsplit(parts._replace(path="/postgres"))
    with psycopg.connect(admin, autocommit=True, connect_timeout=5) as conn:
        if not conn.execute("SELECT 1 FROM pg_database WHERE datname = %s", (DB,)).fetchone():
            conn.execute(f"CREATE DATABASE {DB}")
            print(f"created database {DB}")
    with psycopg.connect(url, connect_timeout=5) as conn:
        for t in reversed(list(demo_data.TABLES)):
            conn.execute(f"DROP TABLE IF EXISTS {t}")
        for t in demo_data.TABLES:
            conn.execute(demo_data.ddl(t))
            rows = demo_data.ROWS[t]
            if rows:
                with conn.cursor() as cur:
                    cur.executemany(f"INSERT INTO {t} VALUES ({', '.join(['%s'] * len(rows[0]))})", rows)
            print(f"  {t:14} {len(rows):3} rows")
        conn.commit()
        check = conn.execute(
            "SELECT v.name, SUM(i.amount) - c.contract_value FROM vendors v "
            "JOIN contracts c ON c.vendor_id = v.vendor_id AND c.quarter = '2026-Q3' "
            "JOIN invoices i ON i.vendor_id = v.vendor_id AND i.status = 'paid' "
            "AND i.invoice_date BETWEEN '2026-07-01' AND '2026-09-30' "
            "GROUP BY v.name, c.contract_value HAVING SUM(i.amount) > c.contract_value").fetchall()
    got = {n: float(v) for n, v in check}
    ok = got == demo_data.EXPECTED_Q3_OVERPAID
    print(f"Q3 overpaid vendors: {got} ({'as expected' if ok else 'UNEXPECTED'})")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
