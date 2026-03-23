import os
import sys
from datetime import datetime

import requests
from dotenv import load_dotenv
from sqlalchemy.orm import Session
from tqdm import tqdm

# Allow running from any working directory
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
load_dotenv(os.path.join(BASE_DIR, ".env"))

sys.path.insert(0, BASE_DIR)
from src.models import CRLRecord, init_db

API_KEY = os.environ.get("OPENFDA_API_KEY")
BASE_URL = "https://api.fda.gov/transparency/crl.json"
LIMIT = 100
DATE_FROM = "01/01/2021"
DATE_TO = datetime.today().strftime("%m/%d/%Y")


def derive_application_type(application_number) -> str:
    if not application_number:
        return "Unknown"
    if isinstance(application_number, list):
        application_number = " ".join(application_number)
    upper = application_number.upper()
    if "BLA" in upper:
        return "BLA"
    elif "NDA" in upper:
        return "NDA"
    return "Unknown"


def derive_outcome(letter_type: str) -> str:
    if not letter_type:
        return "Other"
    mapping = {
        "APPROVAL": "Approved",
        "TENTATIVE APPROVAL": "Tentative Approval",
        "COMPLETE RESPONSE": "Not Approved",
        "RESCIND COMPLETE RESPONSE": "Rescinded",
    }
    return mapping.get(letter_type.strip().upper(), "Other")


def fetch_page(skip: int) -> dict:
    params = {
        "search": f'letter_date:["{DATE_FROM}" TO "{DATE_TO}"]',
        "limit": LIMIT,
        "skip": skip,
    }
    if API_KEY:
        params["api_key"] = API_KEY

    response = requests.get(BASE_URL, params=params, timeout=30)
    response.raise_for_status()
    return response.json()


def fetch_all():
    engine = init_db()

    # First request to get total count
    print(f"Fetching CRL records from {DATE_FROM} to {DATE_TO}...")
    first_page = fetch_page(skip=0)
    total = first_page.get("meta", {}).get("results", {}).get("total", 0)
    print(f"Total records found: {total}\n")

    added = 0
    skipped = 0

    with Session(engine) as session:
        all_pages = range(0, total, LIMIT)
        with tqdm(total=total, unit="record", desc="Processing") as pbar:
            for page_num, skip in enumerate(all_pages):
                if skip == 0:
                    data = first_page
                else:
                    data = fetch_page(skip=skip)

                records = data.get("results", [])

                for item in records:
                    file_name = item.get("file_name")

                    # Skip duplicates
                    exists = session.query(CRLRecord).filter_by(file_name=file_name).first()
                    if exists:
                        skipped += 1
                        pbar.update(1)
                        continue

                    # approver_center is a list — join to pipe-separated string
                    approver_center = item.get("approver_center") or []
                    if isinstance(approver_center, list):
                        approver_center = " | ".join(approver_center)
                    approver_center = approver_center.replace(
                        "Center tor Drug Evaluation and Research",
                        "Center for Drug Evaluation and Research",
                    )

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

    print(f"\nDone. Records added: {added} | Records skipped (duplicates): {skipped}")


if __name__ == "__main__":
    fetch_all()
