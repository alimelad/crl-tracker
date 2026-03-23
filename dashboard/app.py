import os
import sys

import pandas as pd
import streamlit as st
from sqlalchemy.orm import Session
from sqlalchemy import create_engine

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, BASE_DIR)

DB_PATH = os.path.join(BASE_DIR, "db", "crl.db")
DATABASE_URL = f"sqlite:///{DB_PATH}"

ASSETS_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "assets")
LOGO_PATH = os.path.join(ASSETS_DIR, "logo.png")

st.set_page_config(
    page_title="FDA CRL Tracker",
    page_icon=LOGO_PATH if os.path.exists(LOGO_PATH) else "💊",
    layout="wide",
)


@st.cache_data
def load_data():
    engine = create_engine(DATABASE_URL, echo=False)
    with engine.connect() as conn:
        df = pd.read_sql("SELECT * FROM crl_records", conn)

    # Parse letter_date to datetime for filtering/sorting
    df["letter_date_dt"] = pd.to_datetime(df["letter_date"], format="%m/%d/%Y", errors="coerce")
    df["year"] = df["letter_date_dt"].dt.year

    return df


df_all = load_data()

# ---------------------------------------------------------------------------
# Logo + Title
# ---------------------------------------------------------------------------
if os.path.exists(LOGO_PATH):
    st.image(LOGO_PATH, width=220)
st.title("FDA CRL Tracker")

# ---------------------------------------------------------------------------
# Sidebar filters
# ---------------------------------------------------------------------------
st.sidebar.header("Filters")

# Date range
min_date = df_all["letter_date_dt"].min().date()
max_date = df_all["letter_date_dt"].max().date()
date_from, date_to = st.sidebar.date_input(
    "Letter date range",
    value=(min_date, max_date),
    min_value=min_date,
    max_value=max_date,
)

# Outcome
outcome_options = ["All", "Approved", "Not Approved", "Tentative Approval", "Other"]
selected_outcome = st.sidebar.selectbox("Outcome", outcome_options)

# Application type
app_type_options = ["All", "NDA", "BLA", "Unknown"]
selected_app_type = st.sidebar.selectbox("Application Type", app_type_options)

# Approval center — flatten pipe-separated values into unique list
all_centers = sorted(
    set(
        center.strip()
        for val in df_all["approval_center"].dropna()
        for center in val.split("|")
        if center.strip()
    )
)
selected_centers = st.sidebar.multiselect("Approval Center", all_centers)

# Company name text search
company_search = st.sidebar.text_input("Search company name")

# ---------------------------------------------------------------------------
# Apply filters
# ---------------------------------------------------------------------------
df = df_all.copy()

df = df[
    (df["letter_date_dt"].dt.date >= date_from) &
    (df["letter_date_dt"].dt.date <= date_to)
]

if selected_outcome != "All":
    df = df[df["outcome"] == selected_outcome]

if selected_app_type != "All":
    df = df[df["application_type"] == selected_app_type]

if selected_centers:
    df = df[
        df["approval_center"].apply(
            lambda val: any(
                c.strip() in selected_centers
                for c in (val or "").split("|")
            )
        )
    ]

if company_search:
    df = df[df["company_name"].str.contains(company_search, case=False, na=False)]

# ---------------------------------------------------------------------------
# Metric cards
# ---------------------------------------------------------------------------
col1, col2, col3, col4 = st.columns(4)
col1.metric("Total Records", len(df))
col2.metric("Not Approved", len(df[df["outcome"] == "Not Approved"]))
col3.metric("Approved", len(df[df["outcome"] == "Approved"]))
col4.metric("Tentative Approval", len(df[df["outcome"] == "Tentative Approval"]))

st.divider()

# ---------------------------------------------------------------------------
# Charts
# ---------------------------------------------------------------------------
chart_col1, chart_col2 = st.columns(2)
chart_col3, chart_col4 = st.columns(2)

with chart_col1:
    st.subheader("Records by Year")
    year_counts = df["year"].value_counts().sort_index().reset_index()
    year_counts.columns = ["Year", "Count"]
    year_counts["Year"] = year_counts["Year"].astype(str)
    st.bar_chart(year_counts.set_index("Year")["Count"])

with chart_col2:
    st.subheader("Records by Outcome")
    outcome_counts = df["outcome"].value_counts().reset_index()
    outcome_counts.columns = ["Outcome", "Count"]
    st.bar_chart(outcome_counts.set_index("Outcome")["Count"])

with chart_col3:
    st.subheader("Records by Application Type")
    app_type_counts = df["application_type"].value_counts().reset_index()
    app_type_counts.columns = ["Application Type", "Count"]
    st.bar_chart(app_type_counts.set_index("Application Type")["Count"])

with chart_col4:
    st.subheader("Top 15 Approval Centers")
    center_counts = (
        df["approval_center"]
        .dropna()
        .apply(lambda val: [c.strip() for c in val.split("|") if c.strip()])
        .explode()
        .value_counts()
        .head(15)
        .reset_index()
    )
    center_counts.columns = ["Center", "Count"]
    st.bar_chart(center_counts.set_index("Center")["Count"])

st.divider()

# ---------------------------------------------------------------------------
# Data table
# ---------------------------------------------------------------------------
st.subheader("Records")

TABLE_COLS = [
    "letter_date",
    "company_name",
    "application_number",
    "application_type",
    "letter_type",
    "outcome",
    "approval_center",
]

df_display = df[TABLE_COLS].sort_values("letter_date", ascending=False).reset_index(drop=True)

selection = st.dataframe(
    df_display,
    use_container_width=True,
    hide_index=False,
    on_select="rerun",
    selection_mode="single-row",
)

# ---------------------------------------------------------------------------
# Full letter text on row selection
# ---------------------------------------------------------------------------
selected_rows = selection.selection.rows if selection.selection else []

if selected_rows:
    row_idx = selected_rows[0]
    selected_record = df_display.iloc[row_idx]

    # Match back to full df to get full_text
    match = df[
        (df["letter_date"] == selected_record["letter_date"]) &
        (df["company_name"] == selected_record["company_name"]) &
        (df["application_number"] == selected_record["application_number"])
    ]

    if not match.empty:
        record = match.iloc[0]
        with st.expander(
            f"Full Letter Text — {record['company_name']} ({record['letter_date']})",
            expanded=True,
        ):
            st.markdown(f"**File:** {record['file_name']}")
            st.markdown(f"**Letter Type:** {record['letter_type']}  |  **Outcome:** {record['outcome']}")
            st.markdown(f"**Application:** {record['application_number']}  |  **Type:** {record['application_type']}")
            st.markdown(f"**Company Rep:** {record['company_rep']}")
            st.markdown(f"**Approval Center:** {record['approval_center']}")
            st.divider()
            st.text(record["full_text"] or "No full text available.")

# ---------------------------------------------------------------------------
# Footer note + branding
# ---------------------------------------------------------------------------
st.divider()
st.caption(
    "Note: **outcome** and **application_type** are derived fields. "
    "Outcome is derived from letter_type; application_type is derived from application_number."
)

st.markdown(
    """
    <hr style="border: none; border-top: 1px solid #e0e0e0; margin-top: 2rem;">
    <div style="text-align: center; color: #999999; font-size: 0.8rem; padding-bottom: 1rem;">
        <p style="margin: 0.2rem 0;">Created by Alimelad</p>
        <p style="margin: 0.2rem 0;">Questions? Reach out to <a href="mailto:ali.melad@aei.org" style="color: #999999;">ali.melad@aei.org</a></p>
    </div>
    """,
    unsafe_allow_html=True,
)
