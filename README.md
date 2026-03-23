# FDA CRL Tracker

A live dashboard that tracks FDA Complete Response Letters (CRLs) pulled directly from the openFDA API. Browse, filter, and explore every CRL issued since 2021, with cross-referenced approval data showing whether each application was eventually approved.

---

## Features

- Tracks all FDA Complete Response Letters from 2021 to present
- Distinguishes between NDA (New Drug Application) and BLA (Biologics License Application) types
- Shows the outcome for each letter: Not Approved, Approved, Tentative Approval, or Rescinded
- Cross-references the FDA drugsfda endpoint to show whether each application was eventually approved and on what date
- Displays the full text of any individual letter
- Filterable by date range, outcome, application type, approval center, and company name
- Export the current filtered view to CSV with a dynamic filename
- Auto-refreshes every hour when deployed on Streamlit Cloud
- Visual charts including a pie chart for outcome breakdown, a donut chart for NDA vs BLA split, bar charts by year and approval center, and a grouped bar chart for eventually approved by year

---

## Tech Stack

- Python
- Streamlit
- SQLAlchemy
- SQLite
- openFDA API

---

## Local Setup

**1. Clone the repository**

```bash
git clone https://github.com/alimelad/crl-tracker.git
cd crl-tracker
```

**2. Create a virtual environment and install dependencies**

```bash
python -m venv venv
venv\Scripts\activate        # Windows
# source venv/bin/activate   # Mac/Linux
pip install -r requirements.txt
```

**3. Add your openFDA API key**

Create a `.env` file in the root of the project:

```
OPENFDA_API_KEY=your_key_here
```

Get a free API key at [https://open.fda.gov/apis/authentication/](https://open.fda.gov/apis/authentication/).

**4. Load initial data**

```bash
python src/fetch.py
```

This fetches all CRL records from 01/01/2021 to today and saves them to the local SQLite database at `db/crl.db`.

**5. Populate approval cross-reference data**

```bash
python src/crossref.py
```

This queries the FDA drugsfda endpoint for each unique application number and records whether it was eventually approved, along with the approval date.

**6. Run the dashboard**

```bash
streamlit run dashboard/app.py
```

The dashboard will open at [http://localhost:8501](http://localhost:8501).

**Keeping data up to date**

Run the update script periodically to pull in new letters without re-fetching everything:

```bash
python src/update.py
```

---

## Deployment

This app is deployed on [Streamlit Cloud](https://share.streamlit.io). The main file is set to `dashboard/app.py`.

When no local SQLite database is present (as on Streamlit Cloud), the app fetches data directly from the openFDA API on load and caches it for one hour. The API key is stored securely under App Settings > Secrets in the Streamlit Cloud dashboard:

```toml
OPENFDA_API_KEY = "your_key_here"
```

---

## Data Source

All data is sourced from the [openFDA API](https://open.fda.gov/), maintained by the U.S. Food and Drug Administration. This project is not affiliated with or endorsed by the FDA.

---

Created by [Alimelad](mailto:ali.melad@aei.org)
