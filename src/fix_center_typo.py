import os
import sys
from sqlalchemy import create_engine, text

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DB_PATH = os.path.join(BASE_DIR, "db", "crl.db")
DATABASE_URL = f"sqlite:///{DB_PATH}"

engine = create_engine(DATABASE_URL)

with engine.connect() as conn:
    result = conn.execute(
        text("""
            UPDATE crl_records
            SET approval_center = REPLACE(
                approval_center,
                'Center tor Drug Evaluation and Research',
                'Center for Drug Evaluation and Research'
            )
            WHERE approval_center LIKE '%Center tor Drug Evaluation and Research%'
        """)
    )
    conn.commit()
    print(f"Records updated: {result.rowcount}")
