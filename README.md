# Lead Management App — Free Deployment Pipeline

```text
Browser (any state/location)
        |
GitHub repo  --push-->  CI check (GitHub Actions)
        |
Streamlit Community Cloud (auto-deploys on push to main)
        |
UptimeRobot  --pings every 5-10 min-->  keeps the app awake
        |
Google Sheet backend (Leads_Master, Users_Master, Dropdown_Master, Activity_Log)
```

This version is functionally the same app as before, with the performance and
reliability problems fixed at the code level — see "What changed" below.

## Files

```text
app.py
requirements.txt
.streamlit/config.toml
.streamlit/secrets.example.toml
.github/workflows/ci.yml
README.md
.gitignore
```

## What changed from the original version

1. **Cached reads.** Every read from Google Sheets (`read_df`) is now cached
   for 30 seconds (`CACHE_TTL_SECONDS`). Switching tabs or changing a filter
   no longer re-fetches the whole sheet — it reuses the cached data. A
   "Refresh data now" button in the sidebar force-clears the cache if you
   need to see a change immediately.
2. **Batched writes.** `update_lead()` used to call the Google API once per
   changed field (a 6-field update was 6+ round trips). It now sends all
   changes in a single `batch_update` call.
3. **One fetch instead of two when adding a lead.** `add_lead()` used to
   read the whole Leads sheet twice (once for the duplicate check, once for
   the next Opportunity ID). It now reads once and reuses the data.
4. **Batched dropdown seeding.** `seed_dropdowns()` used to insert ~45 rows
   one API call at a time. It now inserts them in a single batched call.
5. **Automatic retry with backoff.** Google Sheets' free quota is roughly
   60 reads/writes per minute per user. Hitting that limit used to surface
   as a hard error. Calls now retry up to 3 times with a short backoff
   before failing, which absorbs most transient rate-limit hiccups.
6. **Secrets hygiene.** `.gitignore` now blocks `secrets.toml`,
   `service_account.json`, and `.pem` files from ever being committed. CI
   also fails the build if either file is detected in the repo, as a second
   line of defense.
7. **CI pipeline.** Every push to `main` runs a GitHub Actions check that
   installs dependencies, verifies `app.py` has no syntax errors, and
   blocks the push if secrets were accidentally committed — before
   Streamlit Cloud ever sees it.

## ⚠️ If you're migrating from the old version: rotate your key first

The previous zip had a real `service_account.json` and filled-in
`secrets.toml` bundled inside it. Treat that service account key as
compromised:

1. Go to Google Cloud Console → IAM & Admin → Service Accounts.
2. Find the service account, delete the old key, generate a new one.
3. Use the new key's values when filling in Streamlit Cloud secrets below.
4. Never put real credentials in any file that gets zipped, emailed, or
   committed — only in Streamlit Cloud's Secrets panel (Step 4) or a local
   `.streamlit/secrets.toml` that `.gitignore` excludes.

## Step 1: Google Sheet

Create a Google Sheet (any name). Copy the Sheet ID from its URL:

```text
https://docs.google.com/spreadsheets/d/SHEET_ID_HERE/edit
```

## Step 2: Google service account

1. Open Google Cloud Console, create/select a project.
2. Enable the Google Sheets API and Google Drive API.
3. Create a Service Account, then create a JSON key for it.
4. Copy the service account's email address.
5. Share your Google Sheet with that email as **Editor**.

## Step 3: Push to GitHub

```bash
git init
git add .
git commit -m "Lead management app"
git branch -M main
git remote add origin https://github.com/YOUR_USERNAME/YOUR_REPO.git
git push -u origin main
```

Do **not** add `.streamlit/secrets.toml` or `service_account.json` — they're
already excluded by `.gitignore`. CI will block the push if they slip in
anyway.

## Step 4: Deploy on Streamlit Community Cloud (free)

1. Go to share.streamlit.io and sign in with GitHub.
2. "Create app" → select your repo and branch `main` → main file `app.py`.
3. Deploy.
4. Once deployed: App menu → **Settings → Secrets** → paste the contents of
   `.streamlit/secrets.example.toml`, filled in with your real Sheet ID and
   service account JSON values.
5. Reboot the app.

Your app will be live at:

```text
https://your-app-name.streamlit.app
```

This URL works identically for users in any state or location — it's a
public web page, not tied to a region.

## Step 5: First-time setup inside the app

Open the deployed app → **Setup** tab → "Create required Google Sheet tabs".
This creates:

```text
Leads_Master
Users_Master
Dropdown_Master
Activity_Log
```

Then fill in `Users_Master` in the Google Sheet directly:

```text
Name | Email | State | City | Role | Manager | Active
Naveen | name@company.com | Maharashtra | Mumbai | admin |  | Yes
```

Role meaning: `user` sees only their own leads, `manager` sees leads in
their configured state, `admin` sees everything. Only rows with
`Active = Yes` can log in.

## Step 6: Keep the app awake (free)

Streamlit Community Cloud's free tier sleeps an app after a period of
inactivity, causing a slow cold-start (10-30s) for the next visitor. To
prevent that for free:

1. Go to uptimerobot.com → free account.
2. Add a new **HTTP(s)** monitor.
3. URL: your app's `https://your-app-name.streamlit.app` link.
4. Interval: every 5 minutes.

UptimeRobot will visit the app on a schedule, which keeps it from going to
sleep, so real users get a fast load instead of a cold start.

## Step 7: Verify the pipeline works end to end

- Push a small change to `app.py` on a branch, open a PR — confirm the CI
  check in the **Actions** tab on GitHub passes.
- Merge to `main` — confirm Streamlit Cloud picks up the change and
  redeploys automatically (Streamlit Cloud watches `main` by default).
- Open the live URL from a different network (e.g., phone on mobile data)
  to confirm it's reachable from outside your office network.
- In the app sidebar, confirm "Refresh data now" pulls a row you just added
  directly in the Google Sheet.

## Operating notes

- **Data freshness:** changes made directly in the Google Sheet (outside the
  app) take up to `CACHE_TTL_SECONDS` (30s) to appear in the app, or use the
  sidebar "Refresh data now" button for an instant pull.
- **Rate limits:** Google Sheets free quota is roughly 60 read/write
  requests per minute per user. The caching and batching changes above
  drastically reduce how often the app hits that ceiling, and failed calls
  now auto-retry. If you still see quota errors with this many users, that's
  the signal to migrate off Google Sheets to a real database — not a hosting
  problem.
- **When to stop being free:** if the team grows past roughly 20-30 active
  users, or Sheets quota errors become frequent, the next step is a small
  always-on host (~$5-7/month on Render/Railway) plus optionally a real
  database (e.g. free-tier Postgres on Supabase) instead of Google Sheets.
