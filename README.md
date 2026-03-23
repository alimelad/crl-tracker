# FDA CRL Tracker

A Streamlit dashboard for tracking FDA Complete Response Letters (CRLs) and other drug application action letters sourced from the [openFDA Transparency endpoint](https://open.fda.gov/).

---

## What It Does

This tool fetches, stores, and visualizes FDA action letters — primarily Complete Response Letters (CRLs) — issued to pharmaceutical companies in response to NDA (New Drug Application) and BLA (Biologics License Application) submissions.

It provides a filterable, searchable dashboard that lets you explore:
- Which companies received CRLs and when
- Whether applications were ultimately approved, denied, or received a tentative approval
- Which FDA review centers issued the letters
- Full text of each letter

---

## What It Fetches

Data is pulled from the openFDA CRL API endpoint:

```
https://api.fda.gov/transparency/crl.json
```

Each record includes the following fields from the API:

| Field | Description |
|---|---|
| `file_name` | Unique identifier for the letter file |
| `application_number` | FDA application number (e.g. NDA123456, BLA761234) |
| `letter_type` | Type of action letter (e.g. COMPLETE RESPONSE, APPROVAL) |
| `letter_date` | Date the letter was issued |
| `company_name` | Name of the applicant company |
| `company_rep` | Company representative named in the letter |
| `company_address` | Company mailing address |
| `approver_name` | Name of the FDA official who signed the letter |
| `approver_title` | Title of the signing FDA official |
| `approver_center` | FDA center(s) that issued the letter (e.g. CDER, CBER) |
| `full_text` | Full plain-text content of the letter |

The initial fetch (`src/fetch.py`) pulls all records from **01/01/2021 to today**. The update script (`src/update.py`) fetches only records newer than the most recent letter date already in the database.

---

## What It Aggregates

The following fields are **derived** and stored alongside the raw data:

### `application_type`
Derived from `application_number`:
- Contains `BLA` → **BLA** (Biologics License Application)
- Contains `NDA` → **NDA** (New Drug Application)
- Neither → **Unknown**

### `outcome`
Derived from `letter_type`:

| `letter_type` | `outcome` |
|---|---|
| APPROVAL | Approved |
| TENTATIVE APPROVAL | Tentative Approval |
| COMPLETE RESPONSE | Not Approved |
| RESCIND COMPLETE RESPONSE | Rescinded |
| Anything else | Other |

---

## Project Structure

```
crl-tracker/
├── dashboard/
│   ├── app.py              # Streamlit dashboard
│   └── assets/
│       └── logo.png        # Dashboard logo
├── src/
│   ├── models.py           # SQLAlchemy database model
│   ├── fetch.py            # Initial data fetch (2021–today)
│   └── update.py           # Incremental update (new records only)
├── db/                     # SQLite database (gitignored)
├── .streamlit/
│   └── secrets.toml.example
├── .env                    # API key (gitignored)
├── .gitignore
└── requirements.txt
```

---

## Setup

### 1. Clone and install dependencies

```bash
git clone https://github.com/alimelad/crl-tracker.git
cd crl-tracker
python -m venv venv
venv/Scripts/activate        # Windows
# source venv/bin/activate   # Mac/Linux
pip install -r requirements.txt
```

### 2. Add your openFDA API key

Create a `.env` file in the root:

```
OPENFDA_API_KEY=your_key_here
```

Get a free API key at [https://open.fda.gov/apis/authentication/](https://open.fda.gov/apis/authentication/).

### 3. Fetch data

```bash
python src/fetch.py
```

### 4. Run the dashboard

```bash
streamlit run dashboard/app.py
```

---

## Keeping Data Up to Date

Run the update script periodically to pull in new letters:

```bash
python src/update.py
```

It will find the most recent `letter_date` in the database and only fetch records newer than that date.

---

## Deploying to Streamlit Cloud

1. Push this repo to GitHub.
2. Go to [share.streamlit.io](https://share.streamlit.io) and connect the repo.
3. Set the main file path to `dashboard/app.py`.
4. Under **App Settings > Secrets**, add:
   ```toml
   OPENFDA_API_KEY = "your_key_here"
   ```

> **Note:** The SQLite database is not included in the repo. On Streamlit Cloud the database will be empty on first deploy — you'll need to either pre-populate it or adapt the fetch scripts to run on startup.

---

## Data Source

All data is sourced from the [openFDA API](https://open.fda.gov/), maintained by the U.S. Food and Drug Administration. This tool is not affiliated with or endorsed by the FDA.
