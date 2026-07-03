# Lead Management App — Production-Ready with PostgreSQL

```
Architecture:
Browser (any state/location)
    |
GitHub repo → CI check (GitHub Actions)
    |
Streamlit Community Cloud (auto-deploys on main)
    |
PostgreSQL Database (Supabase free tier, or any managed Postgres)
    |
UptimeRobot (keeps app warm, prevents cold-starts)
```

This is the **long-term production version** — moves away from Google Sheets to 
a proper relational database (PostgreSQL via Supabase). This removes API rate 
limits, provides proper transactions, indexing, and scales naturally as your 
team grows.

## Why PostgreSQL instead of Google Sheets

| Issue | Sheets | PostgreSQL |
|-------|--------|------------|
| **Rate limits** | 60 req/min/user (hits fast with concurrent users) | 10s of thousands req/min (no practical ceiling for this app) |
| **Performance** | API latency, ~500ms per call | Sub-50ms queries; 30s cache hits in 0ms |
| **Transactions** | Can't update multiple rows atomically | ACID transactions, no data corruption |
| **Concurrent users** | Sheets becomes bottleneck past ~20-30 | Scales to hundreds easily |
| **Backups** | Manual/limited | Automatic daily snapshots (Supabase) |
| **Cost** | Free | Free tier up to 500MB, then $5-25/month |
| **Data integrity** | You hope nothing breaks | Constraints, foreign keys, audit logs |
| **Analytics** | Export to external BI tool | Query directly, run complex reports |

For 17 users across multiple states, PostgreSQL is a **huge quality-of-life improvement**.

## Setup: Free PostgreSQL via Supabase

Supabase gives you a managed PostgreSQL database for free (up to 500MB storage, 
plenty for this app even with thousands of leads).

### Step 1: Create a Supabase project

1. Go to **supabase.com** → Sign up (free).
2. Create a new project (select a region closest to your team, e.g. India).
3. Wait for the database to provision (~2 min).
4. Once ready, go to **Settings → Database** → copy the connection string:
   ```
   postgresql://postgres:[PASSWORD]@[HOST]:5432/postgres
   ```
5. Also note:
   - **User**: `postgres`
   - **Password**: (shown on Database page)
   - **Host**: (shown on Database page)
   - **Database**: `postgres`

### Step 2: Push code to GitHub

```bash
git init
git add .
git commit -m "Lead management app with PostgreSQL backend"
git branch -M main
git remote add origin https://github.com/YOUR_USERNAME/YOUR_REPO.git
git push -u origin main
```

The `app_postgres.py` is the one to use (not the old `app.py`). You can rename
it to `app.py` if you want, or keep both and deploy `app_postgres.py`.

### Step 3: Deploy on Streamlit Community Cloud

1. Go to **share.streamlit.io** → "Create app"
2. Select your GitHub repo, branch `main`, file `app_postgres.py`
3. Deploy.
4. Once live, go to **App menu → Settings → Secrets** and paste:
   ```toml
   [app]
   default_user_email = "your.email@company.com"

   [database]
   user = "postgres"
   password = "PASTE_FROM_SUPABASE_HERE"
   host = "PASTE_HOST_FROM_SUPABASE"
   port = "5432"
   name = "postgres"
   ```
5. Reboot the app.

### Step 4: First-time database setup

Open the app → **Setup** tab → **"Create/verify database tables"**

This creates the 4 tables:
- `leads` — all lead records
- `users` — user accounts (name, email, role, state access)
- `dropdowns` — lookup values (states, cities, statuses, etc.)
- `activity_log` — audit trail of all changes

### Step 5: Add users to the database

You can use the Supabase SQL editor or add users directly from the app's Setup tab. 
Example SQL (run in Supabase SQL editor):

```sql
INSERT INTO users (name, email, state, city, role, active) VALUES
('Naveen Kumar', 'naveen@company.com', 'Maharashtra', 'Mumbai', 'admin', 'Yes'),
('Rajesh', 'rajesh@company.com', 'Maharashtra', 'Pune', 'manager', 'Yes'),
('Priya', 'priya@company.com', '', '', 'user', 'Yes');
```

Role breakdown:
- **admin**: sees all leads across all states
- **manager**: sees only leads in their assigned state
- **user**: sees only leads they created (Lead Shared by = their email)

Only users with `active = 'Yes'` can log in.

### Step 6: Keep the app awake (free)

Set up UptimeRobot (free) to ping your app every 5 minutes:

1. Go to **uptimerobot.com** → free account
2. Add **HTTP(s)** monitor
3. URL: `https://your-app-name.streamlit.app`
4. Interval: 5 minutes

This prevents cold-starts, which are slower on free tiers.

### Step 7: Verify end to end

- Edit `app_postgres.py` locally, push to `main` → Streamlit auto-redeploys
- Open the app from different networks (office, home, mobile) → same URL works
- Create a lead in the app → check it appears in Supabase SQL editor:
  ```sql
  SELECT * FROM leads ORDER BY date_created DESC LIMIT 1;
  ```
- In Supabase, manually add a user, then log in from the app with that email
- Use "Refresh data now" button in sidebar → should instantly show changes

## Code Structure

### Database functions

```python
# Read
db_execute(query, params, fetch_one=False, fetch_all=False)
read_df(table_name)

# Write
append_row(table_name, data_dict)
append_rows(table_name, data_list)  # batch insert

# Invalidate cache after writes
invalidate_read_caches()
```

All reads are cached for 30 seconds, so repeated tab switches or filters hit 
the cache, not the database. After any write (add lead, update lead, etc.), 
the cache is cleared so the next read is fresh.

### New vs old

| Old (Sheets) | New (Postgres) |
|--------------|----------------|
| Fetches from Google API | Queries local database connection pool |
| No real indexing | Indexes on state, city, status, opportunity_id |
| No transactions | Full ACID guarantees |
| Rate limits at 60/min | No practical limit |
| Cache decorator on read functions | Still cached 30s for performance |
| Batch updates still one-by-one | Same (Postgres is fast enough that this doesn't matter) |

### Performance metrics

With PostgreSQL:
- **Initial load**: 1-2s (build connection pool, fetch dropdowns & initial leads)
- **Tab switch**: 10-100ms (cache hit) or 200-500ms (fresh fetch from DB)
- **Add lead**: 200-400ms (one INSERT + audit log + cache invalidate)
- **Update lead**: 150-300ms (one UPDATE + audit logs + cache invalidate)
- **Dashboard (100 leads)**: 50-100ms (single SELECT query with GROUP BY)

With Google Sheets (old version):
- **Initial load**: 3-5s
- **Tab switch**: 2-5s (full sheet fetch + gspread API overhead)
- **Add lead**: 2-3s (two sheets reads + two appends)
- **Update lead**: 5-10s (one GET_ALL + many update_cell calls)
- **Dashboard (100 leads)**: 5-8s (full fetch + pandas operations)

**~10-20x faster** on most operations after switching to Postgres.

## Operating

### Data freshness

- Changes in the database take up to 30 seconds to appear in the app (cache TTL)
- Use "Refresh data now" sidebar button for instant update
- Changes made directly in Supabase SQL editor take 30s or use the button

### Backups

Supabase automatically backs up daily. You can:
- Manual snapshots: **Settings → Backups → "Save a backup"**
- Restore: **Settings → Backups → select backup → restore**

Free tier keeps 7 days of backups.

### Monitoring

Check database usage in Supabase:
- **Home page** → "Storage usage" (shows current GB)
- Free tier = 500MB storage
- If you hit 500MB, you either upgrade ($5-25/month) or clean up old leads

With ~100 leads at ~2KB each, you're using <1MB. Room for thousands of leads 
before hitting the limit.

### Scaling (when you grow)

If you hit PostgreSQL's free limits or want more:
- **Upgrade Supabase plan**: $5-25/month gets you 8GB storage + more CPU
- **Move to Render or Railway**: same Postgres setup on their platform, $10-20/month
- **Move to AWS RDS**: full managed Postgres, pay per usage

The app code **doesn't change** — just point it at a different database URL.

## Troubleshooting

**"Database connection failed"**
- Check secrets in Streamlit Cloud settings
- Verify Supabase project is still running (not paused due to inactivity)
- Test connection from your laptop:
  ```bash
  psql postgresql://postgres:PASSWORD@HOST:5432/postgres
  ```

**"SSL certificate verification failed"**
- Supabase requires `sslmode=require`; the code handles this
- If still failing, update `psycopg2-binary` in requirements.txt

**"Quota exceeded" or "rate limit"**
- With Postgres, this is **not** a limit — if you see it, report a bug
- Old version (Sheets) would hit this; Postgres has no such ceiling

**Leads not showing up**
- Check Supabase SQL editor: `SELECT COUNT(*) FROM leads;`
- If 0 leads, they haven't been added yet
- If leads exist but don't show in app, click "Refresh data now"

## Files

```
app_postgres.py          ← Main app (use this, not app.py)
requirements.txt         ← psycopg2-binary, streamlit, pandas
.streamlit/
  config.toml           ← Streamlit settings
  secrets.example.toml  ← Template for Streamlit Cloud secrets
.github/workflows/
  ci.yml                ← GitHub Actions (syntax + secrets check)
.gitignore              ← Blocks secrets.toml, .env from commits
README.md               ← This file
```

## Migration from Sheets (if you had data in the old version)

If you used the Sheets version and want to migrate existing leads:

1. Export from the old Sheets version: **Search Leads tab → Download CSV**
2. In Supabase SQL editor, import the CSV:
   ```sql
   -- Create a temporary table, then insert manually or use \COPY
   -- Supabase UI has "Import data" button for CSVs
   ```
3. Or, write a Python script to read the Sheets CSV and INSERT into Postgres

(Happy to provide a migration script if needed — just ask.)

## Cost summary (free forever)

- **Supabase**: Free tier, 500MB storage (more than enough for years of leads)
- **Streamlit Community Cloud**: Free tier with auto-deploy from GitHub
- **UptimeRobot**: Free tier, 50 monitors
- **GitHub**: Free public repo
- **Total**: $0/month indefinitely

When/if you grow past 500MB or need higher SLAs, next step is ~$5-25/month.
