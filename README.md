# Python-only Free Lead Management App

This is the free deployment version:

```text
Streamlit Community Cloud
        ↓
Python Streamlit app
        ↓
Google Sheet backend
```

All 17 people can use one public Streamlit link from different states.

## Files

```text
app.py
requirements.txt
.streamlit/secrets.example.toml
README.md
.gitignore
```

## Features

- Add new lead
- Auto Opportunity ID
- Duplicate check
- Search/filter leads
- Update lead status
- Meeting/proposal/revenue tracking
- Dashboard analysis
- Activity log
- Download filtered CSV
- Google Sheet backend

## Step 1: Create Google Sheet

Create a Google Sheet named:

```text
Lead Management Database
```

Copy Sheet ID from URL:

```text
https://docs.google.com/spreadsheets/d/SHEET_ID_HERE/edit
```

## Step 2: Create Google service account

1. Open Google Cloud Console
2. Create a project
3. Enable Google Sheets API
4. Enable Google Drive API
5. Create Service Account
6. Create JSON key
7. Copy service account email
8. Share your Google Sheet with that service account email as Editor

Example service account email:

```text
lead-app@your-project-id.iam.gserviceaccount.com
```

## Step 3: Run locally

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

Create this file:

```text
.streamlit/secrets.toml
```

Copy content from:

```text
.streamlit/secrets.example.toml
```

Fill real Google Sheet ID and service account JSON values.

Run:

```powershell
streamlit run app.py
```

Open:

```text
http://localhost:8501
```

## Step 4: Deploy free on Streamlit Community Cloud

1. Create GitHub repo
2. Upload:
   - app.py
   - requirements.txt
   - README.md
   - .gitignore
3. Do not upload `.streamlit/secrets.toml`
4. Open Streamlit Community Cloud
5. Create New app
6. Select repo and main file: `app.py`
7. Deploy
8. Go to App → Settings → Secrets
9. Paste secrets
10. Reboot app

Final link will look like:

```text
https://your-lead-app.streamlit.app
```

Share that link with all 17 people.

## Step 5: First setup in app

Open the deployed app and go to:

```text
Setup → Create required Google Sheet tabs
```

It creates:

```text
Leads_Master
Users_Master
Dropdown_Master
Activity_Log
```

## Access logic

At sidebar:

```text
User enters official email only.
Role, state, city, and active status are read from Users_Master.
```

`Users_Master` format:

```text
Name | Email | State | City | Role | Manager | Active
Naveen | 1553218@anarock.com | Maharashtra | Mumbai | admin |  | Yes
Ameya | 108400@anarock.com | Maharashtra | Pune | admin |  | Yes
Varun | Varun.Saxena@Anarock.com | Delhi | Delhi | admin |  | Yes
```

Role meaning:

```text
user = can see own leads
manager = can see leads in their configured state
admin = can see all leads
```

Only users with `Active` set to `Yes` can access the app.
