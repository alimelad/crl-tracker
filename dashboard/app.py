import os
import sys
import time
from datetime import datetime

import pandas as pd
import plotly.express as px
import requests
import streamlit as st
from sqlalchemy import create_engine

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, BASE_DIR)

DB_PATH = os.path.join(BASE_DIR, "db", "crl.db")
DATABASE_URL = f"sqlite:///{DB_PATH}"

ASSETS_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "assets")
LOGO_PATH = os.path.join(ASSETS_DIR, "logo.png")

OPENFDA_URL = "https://api.fda.gov/transparency/crl.json"
DRUGSFDA_URL = "https://api.fda.gov/drug/drugsfda.json"
DATE_FROM = "01/01/2021"

st.set_page_config(
    page_title="FDA CRL Tracker",
    page_icon=LOGO_PATH if os.path.exists(LOGO_PATH) else "💊",
    layout="wide",
)


def _derive_application_type(application_number) -> str:
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


def _derive_outcome(letter_type: str) -> str:
    if not letter_type:
        return "Other"
    mapping = {
        "APPROVAL": "Approved",
        "TENTATIVE APPROVAL": "Tentative Approval",
        "COMPLETE RESPONSE": "Not Approved",
        "RESCIND COMPLETE RESPONSE": "Rescinded",
    }
    return mapping.get(str(letter_type).strip().upper(), "Other")


def _load_from_sqlite() -> pd.DataFrame:
    engine = create_engine(DATABASE_URL, echo=False)
    with engine.connect() as conn:
        return pd.read_sql("SELECT * FROM crl_records", conn)


def _crossref_approval(app_number: str, api_key: str | None) -> tuple[str, str | None]:
    """Query drugsfda for a normalized application number and return (eventually_approved, approval_date)."""
    params = {"search": f'application_number:"{app_number}"', "limit": 1}
    if api_key:
        params["api_key"] = api_key
    try:
        resp = requests.get(DRUGSFDA_URL, params=params, timeout=30)
        if resp.status_code == 404:
            return "No", None
        resp.raise_for_status()
        for result in resp.json().get("results", []):
            for sub in result.get("submissions", []):
                if (
                    sub.get("submission_type", "").upper() == "ORIG"
                    and sub.get("submission_status", "").upper() == "AP"
                ):
                    raw = sub.get("submission_status_date", "")
                    try:
                        approval_date = datetime.strptime(raw, "%Y%m%d").strftime("%Y-%m-%d")
                    except (ValueError, TypeError):
                        approval_date = raw or None
                    return "Yes", approval_date
    except requests.RequestException:
        pass
    return "No", None


def _load_from_api() -> pd.DataFrame:
    api_key = os.environ.get("OPENFDA_API_KEY")
    date_to = datetime.today().strftime("%m/%d/%Y")
    limit = 100
    records = []

    # Get total count
    params = {
        "search": f'letter_date:["{DATE_FROM}" TO "{date_to}"]',
        "limit": 1,
        "skip": 0,
    }
    if api_key:
        params["api_key"] = api_key

    resp = requests.get(OPENFDA_URL, params=params, timeout=30)
    resp.raise_for_status()
    total = resp.json().get("meta", {}).get("results", {}).get("total", 0)

    status = st.status(f"Fetching {total} CRL records from openFDA...", expanded=False)

    for skip in range(0, total, limit):
        params = {
            "search": f'letter_date:["{DATE_FROM}" TO "{date_to}"]',
            "limit": limit,
            "skip": skip,
        }
        if api_key:
            params["api_key"] = api_key

        resp = requests.get(OPENFDA_URL, params=params, timeout=30)
        resp.raise_for_status()

        for item in resp.json().get("results", []):
            application_number = item.get("application_number", "") or ""
            if isinstance(application_number, list):
                application_number = " ".join(application_number)
            letter_type = item.get("letter_type", "") or ""

            approver_center = item.get("approver_center") or []
            if isinstance(approver_center, list):
                approver_center = " | ".join(approver_center)
            approver_center = approver_center.replace(
                "Center tor Drug Evaluation and Research",
                "Center for Drug Evaluation and Research",
            )

            records.append({
                "file_name":          item.get("file_name"),
                "application_number": application_number,
                "letter_type":        letter_type,
                "letter_date":        item.get("letter_date"),
                "company_name":       item.get("company_name"),
                "company_rep":        item.get("company_rep"),
                "company_address":    item.get("company_address"),
                "approval_name":      item.get("approver_name"),
                "approval_title":     item.get("approver_title"),
                "approval_center":    approver_center,
                "full_text":          item.get("full_text"),
                "application_type":   _derive_application_type(application_number),
                "outcome":            _derive_outcome(letter_type),
                "date_fetched":       datetime.utcnow().isoformat(),
                "eventually_approved": None,
                "approval_date":       None,
            })

        status.update(label=f"Fetched {min(skip + limit, total)} / {total} CRL records...")

    status.update(label=f"Cross-referencing approvals for {len(records)} records...", state="running")

    # Build unique normalized application numbers -> list of record indices
    app_index: dict[str, list[int]] = {}
    for i, rec in enumerate(records):
        normalized = (rec["application_number"] or "").replace(" ", "").strip()
        if normalized:
            app_index.setdefault(normalized, []).append(i)

    crossref_cache: dict[str, tuple[str, str | None]] = {}
    for n, (app_number, indices) in enumerate(app_index.items()):
        eventually_approved, approval_date = _crossref_approval(app_number, api_key)
        crossref_cache[app_number] = (eventually_approved, approval_date)
        for i in indices:
            records[i]["eventually_approved"] = eventually_approved
            records[i]["approval_date"] = approval_date
        time.sleep(0.3)
        if n % 10 == 0:
            status.update(label=f"Cross-referencing approvals... {n + 1} / {len(app_index)}")

    yes_count = sum(1 for e, _ in crossref_cache.values() if e == "Yes")
    status.update(
        label=f"Done. {len(records)} records loaded — {yes_count} eventually approved.",
        state="complete",
    )
    return pd.DataFrame(records)


@st.cache_data(ttl=3600)
def load_data() -> pd.DataFrame:
    if os.path.exists(DB_PATH):
        df = _load_from_sqlite()
    else:
        df = _load_from_api()

    df["letter_date_dt"] = pd.to_datetime(df["letter_date"], format="%m/%d/%Y", errors="coerce")
    df["year"] = df["letter_date_dt"].dt.year.astype("Int64")

    return df


df_all = load_data()

# ---------------------------------------------------------------------------
# Logo + Title
# ---------------------------------------------------------------------------
if os.path.exists(LOGO_PATH):
    st.image(LOGO_PATH, width=220)
st.title("🏛️ FDA CRL Tracker")

# ---------------------------------------------------------------------------
# Sidebar filters
# ---------------------------------------------------------------------------
st.sidebar.header("Filters")

st.sidebar.markdown("**Date Range**")
min_date = df_all["letter_date_dt"].min().date()
max_date = df_all["letter_date_dt"].max().date()
date_from, date_to = st.sidebar.date_input(
    "Letter date range",
    value=(min_date, max_date),
    min_value=min_date,
    max_value=max_date,
    label_visibility="collapsed",
)

st.sidebar.markdown("**Outcome**")
outcome_options = ["All", "Approved", "Not Approved", "Tentative Approval", "Other"]
selected_outcome = st.sidebar.selectbox("Outcome", outcome_options, label_visibility="collapsed")

st.sidebar.markdown("**Application Type**")
app_type_options = ["All", "NDA", "BLA", "Unknown"]
selected_app_type = st.sidebar.selectbox("Application Type", app_type_options, label_visibility="collapsed")

st.sidebar.markdown("**Approval Center**")
all_centers = sorted(
    set(
        center.strip()
        for val in df_all["approval_center"].dropna()
        for center in val.split("|")
        if center.strip()
    )
)
selected_centers = st.sidebar.multiselect("Approval Center", all_centers, label_visibility="collapsed")

st.sidebar.markdown("**Eventually Approved**")
eventually_approved_options = ["All", "Yes", "No"]
selected_eventually_approved = st.sidebar.selectbox("Eventually Approved", eventually_approved_options, label_visibility="collapsed")

st.sidebar.markdown("**Search**")
company_search = st.sidebar.text_input("Search company name", placeholder="Company name...", label_visibility="collapsed")

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

if selected_eventually_approved != "All":
    df = df[df["eventually_approved"] == selected_eventually_approved]

if company_search:
    df = df[df["company_name"].str.contains(company_search, case=False, na=False)]

# ---------------------------------------------------------------------------
# Metric cards
# ---------------------------------------------------------------------------
col1, col2, col3, col4, col5 = st.columns(5)
col1.metric("Total Records", len(df))
col2.metric("Not Approved", len(df[df["outcome"] == "Not Approved"]))
col3.metric("Approved", len(df[df["outcome"] == "Approved"]))
col4.metric("Tentative Approval", len(df[df["outcome"] == "Tentative Approval"]))
col5.metric("Eventually Approved", len(df[df["eventually_approved"] == "Yes"]))

st.divider()

# ---------------------------------------------------------------------------
# Charts
# ---------------------------------------------------------------------------
BLUES_TEALS = ["#1d6fa5", "#17a2b8", "#2ca0a0", "#4e9ac7", "#7bc4e2", "#3d8b8b", "#89c4c4", "#5b8db8"]

def chart_title(text: str) -> None:
    st.markdown(f"<p style='font-size:1.1rem; font-weight:700; margin-bottom:0.25rem;'>{text}</p>", unsafe_allow_html=True)

chart_col1, chart_col2 = st.columns(2)
chart_col3, chart_col4 = st.columns(2)
chart_col5, _ = st.columns(2)

with chart_col1:
    chart_title("Records by Year")
    year_counts = (
        df["year"].dropna()
        .astype(int)
        .value_counts()
        .sort_index()
        .reset_index()
    )
    year_counts.columns = ["Year", "Count"]
    year_counts["Year"] = year_counts["Year"].astype(str)
    fig = px.bar(year_counts, x="Year", y="Count", color_discrete_sequence=[BLUES_TEALS[0]])
    fig.update_layout(margin=dict(t=10, b=10), xaxis_title=None, yaxis_title=None)
    st.plotly_chart(fig, use_container_width=True)

with chart_col2:
    chart_title("Records by Outcome")
    outcome_counts = df["outcome"].value_counts().reset_index()
    outcome_counts.columns = ["Outcome", "Count"]
    fig = px.pie(outcome_counts, values="Count", names="Outcome", color_discrete_sequence=BLUES_TEALS)
    fig.update_layout(margin=dict(t=10, b=10), legend=dict(orientation="h", y=-0.15))
    fig.update_traces(textposition="inside", textinfo="percent+label")
    st.plotly_chart(fig, use_container_width=True)

with chart_col3:
    chart_title("Records by Application Type")
    app_type_counts = df["application_type"].value_counts().reset_index()
    app_type_counts.columns = ["Application Type", "Count"]
    fig = px.pie(app_type_counts, values="Count", names="Application Type",
                 hole=0.5, color_discrete_sequence=BLUES_TEALS)
    fig.update_layout(margin=dict(t=10, b=10), legend=dict(orientation="h", y=-0.15))
    fig.update_traces(textposition="inside", textinfo="percent+label")
    st.plotly_chart(fig, use_container_width=True)

with chart_col4:
    chart_title("Top 15 Approval Centers")
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
    fig = px.bar(center_counts, x="Count", y="Center", orientation="h",
                 color_discrete_sequence=[BLUES_TEALS[2]])
    fig.update_layout(margin=dict(t=10, b=10), xaxis_title=None, yaxis_title=None,
                      yaxis=dict(autorange="reversed"))
    st.plotly_chart(fig, use_container_width=True)

with chart_col5:
    chart_title("Eventually Approved by Year")
    if "eventually_approved" in df.columns and df["eventually_approved"].notna().any():
        ea_by_year = (
            df[df["eventually_approved"].isin(["Yes", "No"])].copy()
        )
        ea_by_year["year"] = ea_by_year["year"].dropna().astype(int)
        ea_by_year = (
            ea_by_year.groupby(["year", "eventually_approved"])
            .size()
            .reset_index(name="Count")
        )
        ea_by_year["year"] = ea_by_year["year"].astype(str)
        fig = px.bar(ea_by_year, x="year", y="Count", color="eventually_approved",
                     barmode="group",
                     color_discrete_map={"Yes": BLUES_TEALS[0], "No": BLUES_TEALS[1]},
                     labels={"year": "", "eventually_approved": "Eventually Approved"})
        fig.update_layout(margin=dict(t=10, b=10), xaxis_title=None, yaxis_title=None)
        st.plotly_chart(fig, use_container_width=True)
    else:
        st.caption("No eventually_approved data yet. Run src/crossref.py to populate.")

st.divider()

# ---------------------------------------------------------------------------
# Data table
# ---------------------------------------------------------------------------
st.subheader("Records")

_base_cols = [
    "letter_date",
    "company_name",
    "application_number",
    "application_type",
    "letter_type",
    "outcome",
    "approval_center",
    "eventually_approved",
    "approval_date",
]
TABLE_COLS = [c for c in _base_cols if c in df.columns]

df_display = df[TABLE_COLS].sort_values("letter_date", ascending=False).reset_index(drop=True)
# Ensure letter_date displays as MM/DD/YYYY string
df_display["letter_date"] = pd.to_datetime(df_display["letter_date"], errors="coerce").dt.strftime("%m/%d/%Y").fillna(df_display["letter_date"])

# ---------------------------------------------------------------------------
# CSV export
# ---------------------------------------------------------------------------
_filename_parts = ["crl"]
if selected_app_type != "All":
    _filename_parts.append(selected_app_type)
if selected_outcome != "All":
    _filename_parts.append(selected_outcome.replace(" ", ""))
if date_from.year == date_to.year:
    _filename_parts.append(str(date_from.year))
else:
    _filename_parts.append(f"{date_from.year}-{date_to.year}")
if company_search:
    _filename_parts.append(company_search.replace(" ", "_"))
_csv_filename = "_".join(_filename_parts) + ".csv"

st.download_button(
    label="Download Current View as CSV",
    data=df_display.to_csv(index=False).encode("utf-8"),
    file_name=_csv_filename,
    mime="text/csv",
)

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
            # Approval cross-reference banner
            eventually_approved = record.get("eventually_approved") if "eventually_approved" in record.index else None
            approval_date = record.get("approval_date") if "approval_date" in record.index else None
            if eventually_approved == "Yes":
                st.markdown(
                    f'<div style="background-color:#d4edda; border-left:4px solid #28a745; padding:0.6rem 1rem; border-radius:4px; color:#155724; margin-bottom:0.75rem;">'
                    f'✅ <strong>This application was eventually approved on {approval_date}.</strong>'
                    f'</div>',
                    unsafe_allow_html=True,
                )
            elif eventually_approved == "No":
                st.markdown(
                    '<div style="background-color:#f0f0f0; border-left:4px solid #aaaaaa; padding:0.6rem 1rem; border-radius:4px; color:#555555; margin-bottom:0.75rem;">'
                    'No approval found for this application.'
                    '</div>',
                    unsafe_allow_html=True,
                )

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
    <div style="text-align: center; color: #888888; font-size: 0.9rem; padding-bottom: 1rem;">
        <p style="margin: 0.2rem 0;">Created by Alimelad</p>
        <p style="margin: 0.2rem 0;">Questions? Reach out to <a href="mailto:ali.melad@aei.org" style="color: #888888;">ali.melad@aei.org</a></p>
    </div>
    """,
    unsafe_allow_html=True,
)
