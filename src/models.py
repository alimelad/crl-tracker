from sqlalchemy import Column, Integer, String, Text, DateTime, event
from sqlalchemy.orm import declarative_base
from sqlalchemy import create_engine
from datetime import datetime
import os

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DB_PATH = os.path.join(BASE_DIR, "db", "crl.db")
DATABASE_URL = f"sqlite:///{DB_PATH}"

Base = declarative_base()


def _derive_application_type(application_number: str) -> str:
    if not application_number:
        return "Unknown"
    prefix = application_number.strip().upper()[:3]
    if prefix == "BLA":
        return "BLA"
    elif prefix == "NDA":
        return "NDA"
    return "Unknown"


def _derive_outcome(letter_type: str) -> str:
    if not letter_type:
        return "Other"
    mapping = {
        "APPROVAL": "Approved",
        "TENTATIVE APPROVAL": "Tentative Approval",
        "COMPLETE RESPONSE": "Not Approved",
        "RESCIND COMPLETE RESPONSE": "Rescinded",
    }
    return mapping.get(letter_type.strip().upper(), "Other")


class CRLRecord(Base):
    __tablename__ = "crl_records"

    id = Column(Integer, primary_key=True, autoincrement=True)
    file_name = Column(String, unique=True)
    application_number = Column(String)
    letter_type = Column(String)
    letter_date = Column(String)
    company_name = Column(String)
    company_rep = Column(String)
    company_address = Column(String)
    approval_name = Column(String)
    approval_title = Column(String)
    approval_center = Column(String)
    full_text = Column(Text)
    application_type = Column(String)  # BLA, NDA, or Unknown
    outcome = Column(String)           # Approved, Tentative Approval, Not Approved, Rescinded, Other
    date_fetched = Column(DateTime, default=datetime.utcnow)

    def __repr__(self):
        return f"<CRLRecord(file_name={self.file_name!r}, application_number={self.application_number!r}, outcome={self.outcome!r})>"


@event.listens_for(CRLRecord, "before_insert")
def derive_fields_on_insert(mapper, connection, target):
    target.application_type = _derive_application_type(target.application_number or "")
    target.outcome = _derive_outcome(target.letter_type or "")


@event.listens_for(CRLRecord, "before_update")
def derive_fields_on_update(mapper, connection, target):
    target.application_type = _derive_application_type(target.application_number or "")
    target.outcome = _derive_outcome(target.letter_type or "")


def init_db():
    engine = create_engine(DATABASE_URL, echo=False)
    Base.metadata.create_all(engine)
    return engine
