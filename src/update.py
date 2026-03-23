import os
import sys
from datetime import datetime

import requests
from dotenv import load_dotenv
from sqlalchemy.orm import Session
from tqdm import tqdm

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
load_dotenv(os.path.join(BASE_DIR, ".env"))

sys.path.insert(0, BASE_DIR)
from src.models import CRLRecord, init_db
from src.fetch import derive_application_type, derive_outcome

API_KEY = os.getenv("OPENFDA_API_KEY")
BASE_URL = "https://api.fda.gov/transparency/crl.json"
LIMIT = 100


def fetch_page(date_from: str, date_to: str, skip: int) -> dict:
    params = {
        "search": f'letter_date:["{date_from}" TO "{date_to}"]',
        "limit": LIMIT,
        "skip": skip,
    }
    if API_KEY:
        params["api_key"] = API_KEY

    response = requests.get(BASE_URL, params=params, timeout=30)
    response.raise_for_status()
    return response.json()


def update():
    engine = init_db()

    with Session(engine) as session:
        latest = session.query(CRLRecord.letter_date).order_by(CRLRecord.letter_date.desc()).first()

    if not latest or not latest[0]:
        print("No existing records found. Run fetch.py for an initial load.")
        return

    date_from = latest[0].strip()
    date_to = datetime.today().strftime("%m/%d/%Y")

    print(f"Most recent letter_date in DB: {date_from}")
    print(f"Fetching records from {date_from} to {date_to}...")

    first_page = fetch_page(date_from, date_to, skip=0)
    total = first_page.get("meta", {}).get("results", {}).get("total", 0)
    print(f"Total records in date range: {total}\n")

    if total == 0:
        print("No new records found.")
        return

    added = 0
    skipped = 0

    with Session(engine) as session:
        with tqdm(total=total, unit="record", desc="Processing") as pbar:
            for skip in range(0, total, LIMIT):
                data = first_page if skip == 0 else fetch_page(date_from, date_to, skip)

                for item in data.get("results", []):
                    file_name = item.get("file_name")

                    exists = session.query(CRLRecord).filter_by(file_name=file_name).first()
                    if exists:
                        skipped += 1
                        pbar.update(1)
                        continue

                    approver_center = item.get("approver_center") or []
                    if isinstance(approver_center, list):
                        approver_center = " | ".join(approver_center)

                    application_number = item.get("application_number", "") or ""
                    if isinstance(application_number, list):
                        application_number = " ".join(application_number)
                    letter_type = item.get("letter_type", "") or ""

                    record = CRLRecord(
                        file_name=file_name,
                        application_number=application_number,
                        letter_type=letter_type,
                        letter_date=item.get("letter_date"),
                        company_name=item.get("company_name"),
                        company_rep=item.get("company_rep"),
                        company_address=item.get("company_address"),
                        approval_name=item.get("approver_name"),
                        approval_title=item.get("approver_title"),
                        approval_center=approver_center,
                        full_text=item.get("full_text"),
                        application_type=derive_application_type(application_number),
                        outcome=derive_outcome(letter_type),
                        date_fetched=datetime.utcnow(),
                    )
                    session.add(record)
                    added += 1
                    pbar.update(1)

                session.commit()

    print(f"\nDone. New records added: {added} | Duplicates skipped: {skipped}")


if __name__ == "__main__":
    update()
