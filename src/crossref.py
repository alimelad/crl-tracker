import os
import sys
import time
from datetime import datetime

import requests
from dotenv import load_dotenv
from sqlalchemy import text
from sqlalchemy.orm import Session
from tqdm import tqdm

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
load_dotenv(os.path.join(BASE_DIR, ".env"))

sys.path.insert(0, BASE_DIR)
from src.models import CRLRecord, init_db

API_KEY = os.environ.get("OPENFDA_API_KEY")
DRUGSFDA_URL = "https://api.fda.gov/drug/drugsfda.json"


def add_columns_if_missing(engine):
    """Add eventually_approved and approval_date columns if they don't exist."""
    with engine.connect() as conn:
        existing = [
            row[1]
            for row in conn.execute(text("PRAGMA table_info(crl_records)")).fetchall()
        ]
        if "eventually_approved" not in existing:
            conn.execute(text("ALTER TABLE crl_records ADD COLUMN eventually_approved TEXT"))
            print("Added column: eventually_approved")
        if "approval_date" not in existing:
            conn.execute(text("ALTER TABLE crl_records ADD COLUMN approval_date TEXT"))
            print("Added column: approval_date")
        conn.commit()


def normalize_application_number(app_number: str) -> str:
    """Strip spaces from application number: 'NDA 209510' -> 'NDA209510'."""
    return (app_number or "").replace(" ", "").strip()


def query_drugsfda(app_number_normalized: str) -> tuple[str, str | None]:
    """
    Query the drugsfda endpoint for a given application number.
    Returns (eventually_approved, approval_date) where:
      - eventually_approved: 'Yes' or 'No'
      - approval_date: 'YYYY-MM-DD' string or None
    """
    params = {
        "search": f'application_number:"{app_number_normalized}"',
        "limit": 1,
    }
    if API_KEY:
        params["api_key"] = API_KEY

    try:
        resp = requests.get(DRUGSFDA_URL, params=params, timeout=30)
        if resp.status_code == 404:
            return "No", None
        resp.raise_for_status()
        data = resp.json()
    except requests.RequestException:
        return "No", None

    results = data.get("results", [])
    if not results:
        return "No", None

    for result in results:
        for submission in result.get("submissions", []):
            if (
                submission.get("submission_type", "").upper() == "ORIG"
                and submission.get("submission_status", "").upper() == "AP"
            ):
                raw_date = submission.get("submission_status_date", "")
                # Format date from YYYYMMDD to YYYY-MM-DD
                try:
                    approval_date = datetime.strptime(raw_date, "%Y%m%d").strftime("%Y-%m-%d")
                except (ValueError, TypeError):
                    approval_date = raw_date or None
                return "Yes", approval_date

    return "No", None


def run_crossref():
    engine = add_columns_if_missing(engine := init_db()) or engine

    with Session(engine) as session:
        records = session.query(CRLRecord).all()

    if not records:
        print("No records found in database. Run fetch.py first.")
        return

    # Build a map of normalized application_number -> list of record ids
    app_number_map: dict[str, list[int]] = {}
    for record in records:
        normalized = normalize_application_number(record.application_number or "")
        if not normalized:
            continue
        app_number_map.setdefault(normalized, []).append(record.id)

    unique_app_numbers = list(app_number_map.keys())
    print(f"Found {len(records)} records across {len(unique_app_numbers)} unique application numbers.\n")

    results_cache: dict[str, tuple[str, str | None]] = {}
    approved_count = 0
    not_approved_count = 0
    skipped_count = 0

    with tqdm(total=len(unique_app_numbers), unit="app", desc="Cross-referencing") as pbar:
        for app_number in unique_app_numbers:
            eventually_approved, approval_date = query_drugsfda(app_number)
            results_cache[app_number] = (eventually_approved, approval_date)

            if eventually_approved == "Yes":
                approved_count += 1
            else:
                not_approved_count += 1

            pbar.set_postfix(yes=approved_count, no=not_approved_count)
            pbar.update(1)
            time.sleep(0.5)

    # Write results back to the database
    print("\nWriting results to database...")
    with Session(engine) as session:
        for app_number, (eventually_approved, approval_date) in results_cache.items():
            record_ids = app_number_map.get(app_number, [])
            for record_id in record_ids:
                record = session.get(CRLRecord, record_id)
                if record:
                    record.eventually_approved = eventually_approved
                    record.approval_date = approval_date
                else:
                    skipped_count += 1
        session.commit()

    total_updated = sum(len(ids) for ids in app_number_map.values()) - skipped_count
    print(f"\nDone.")
    print(f"  Records updated       : {total_updated}")
    print(f"  Eventually approved   : {sum(len(app_number_map[a]) for a, (e, _) in results_cache.items() if e == 'Yes')}")
    print(f"  Not eventually approved: {sum(len(app_number_map[a]) for a, (e, _) in results_cache.items() if e == 'No')}")
    if skipped_count:
        print(f"  Skipped (not found)   : {skipped_count}")


if __name__ == "__main__":
    run_crossref()
