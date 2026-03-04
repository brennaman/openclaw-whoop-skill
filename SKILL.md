---
name: whoop
version: 1.0.0
description: "Fetch, analyze, chart, and track WHOOP health data (recovery, HRV, RHR, sleep, strain, workouts). Use when: querying any WHOOP metric; generating visual charts or dashboards; planning, monitoring, or reporting on a health experiment (with auto-captured baselines, post-workout segmentation); logging stats to Obsidian; correlating health data with life context; or proactively flagging suppressed recovery trends. Handles OAuth, token refresh, full history pagination, and science-backed metric interpretation (HRV ranges by age, overtraining signals, sleep stage targets, medication context)."
metadata:
  openclaw:
    emoji: "💪"
    homepage: https://www.paulbrennaman.me/lab/whoop-skill
    requires:
      bins:
        - python3
        - git
---

# WHOOP Skill

Fetch, interpret, chart, and track your WHOOP data via the WHOOP Developer API (v2).

## Data Directory

All user-specific data is stored in `~/.config/whoop-skill/` — separate from the skill install directory, which is read-only.

```
~/.config/whoop-skill/
  credentials.json   — OAuth tokens (created by auth.py on first setup)
  experiments.json   — experiment tracking data (created on first `plan` command)
  config.json        — optional path/timezone overrides (copy from config.json.example)
```

The directory and `credentials.json` are created automatically when you run `scripts/auth.py`. You never need to create them manually.

## Setup

> **Before you begin:** This skill requires a WHOOP Developer App to authenticate with the WHOOP API. It's free and takes about 2 minutes to set up.

### Step 0 — Install Python dependencies

```bash
pip install -r requirements.txt
```

### Step 1 — Choose your callback method

Before creating your WHOOP app, decide how you want to handle the OAuth callback:

**Option A — Local server** *(local installs)*
- **Redirect URI:** `http://localhost:8888/callback`
- A temporary server runs on your machine to catch the redirect automatically
- Requires a browser on the same machine as OpenClaw

**Option B — Manual code paste** *(remote/cloud installs)*
- **Redirect URI:** `http://localhost:8888/callback`
- The script prints an authorization URL — open it in any browser, authorize, then copy the `?code=` value from the redirect URL and paste it back into the script
- Nothing passes through any external server — fully self-contained

### Step 2 — Create a WHOOP Developer App

1. Go to https://developer-dashboard.whoop.com
2. Sign in with your WHOOP account
3. Create a Team if prompted (any name works)
4. Click **Create App** and fill in:
   - **App name:** anything (e.g. "My WHOOP Skill")
   - **Redirect URI:** the URI from Step 1 (Option A or B)
   - **Scopes:** select all `read:*` scopes + `offline`
5. Copy your **Client ID** and **Client Secret** — you'll need them in the next step

### Step 3 — Run the setup script

```bash
python3 scripts/auth.py
```

This will:
1. Prompt you for your Client ID and Client Secret
2. Ask which callback method you chose in Step 1 (local server or manual)
3. Walk you through the authorization flow
4. Save credentials to `~/.config/whoop-skill/credentials.json`

**Customize paths (optional):**
Copy `config.json.example` from the skill root to `~/.config/whoop-skill/config.json` and edit to override defaults:
```json
{
  "creds_path": "~/.config/whoop-skill/credentials.json",
  "vault_path": "~/my-obsidian-vault",
  "daily_notes_subdir": "Daily Notes",
  "timezone": "America/New_York",
  "logged_by": "Assistant"
}
```

## Workflow

1. Load credentials from `~/.config/whoop-skill/credentials.json`
2. If `expires_at` is in the past (or within 60s), call `scripts/refresh_token.py` to get a new access token and update the file
3. Call the appropriate endpoint (see `references/api.md`)
4. Parse and present the data in plain language

## Common Requests

- **"How's my recovery today?"** → GET latest recovery score, HRV, RHR
- **"How did I sleep?"** → GET latest sleep (performance %, stages, duration)
- **"What's my strain today?"** → GET latest cycle strain + avg HR
- **"Show my recent workouts"** → GET workout collection (last 5–7) via `/activity/workout`
- **"Give me a health summary"** → Combine recovery + sleep + today's cycle

## Token Refresh

Run `scripts/refresh_token.py` when the access token is expired. It reads/writes `~/.config/whoop-skill/credentials.json` automatically.

To re-auth from scratch, run `scripts/auth.py` again.

## API Base URL

`https://api.prod.whoop.com/developer/v2`

All requests: `Authorization: Bearer <access_token>`

See `references/api.md` for endpoint details, scopes, and response shapes.

---

## Fetching Data (`scripts/fetch.py`)

General-purpose API fetcher. Used internally by other scripts.

```bash
# Latest recovery
python3 scripts/fetch.py /recovery --limit 1

# Last 30 days of sleep
python3 scripts/fetch.py /activity/sleep --limit 30

# Workouts last 7 days
python3 scripts/fetch.py /activity/workout --limit 7

# Date-range fetch
python3 scripts/fetch.py /recovery --start 2026-02-01 --end 2026-02-28

# User profile
python3 scripts/fetch.py /user/profile/basic
```

Output is JSON to stdout.

---

## Charting (`scripts/chart.py`)

Generates self-contained HTML charts using Chart.js (CDN). Dark theme with stat cards showing avg/min/max + trend arrow. Opens in browser automatically.

### Chart Types

| Chart | Description |
|-------|-------------|
| `recovery` | Bar chart color-coded green/yellow/red by recovery score |
| `sleep` | Stacked bar: REM / Deep / Light / Awake per night |
| `hrv` | Line chart with 7-day rolling average overlay |
| `strain` | Bar chart with calories as secondary line axis |
| `dashboard` | 2×2 grid of all four charts |

### Usage

```bash
# Recovery chart (30 days)
python3 scripts/chart.py --chart recovery --days 30

# Full dashboard
python3 scripts/chart.py --chart dashboard --days 30 --output ~/whoop-dashboard.html

# HRV trend (90 days), don't auto-open
python3 scripts/chart.py --chart hrv --days 90 --no-open

# Sleep breakdown
python3 scripts/chart.py --chart sleep --days 14

# Strain + calories
python3 scripts/chart.py --chart strain --days 21
```

### Flags

| Flag | Default | Description |
|------|---------|-------------|
| `--chart` | (required) | Chart type: recovery, sleep, hrv, strain, dashboard |
| `--days` | 30 | Days of history to fetch |
| `--output` | `/tmp/whoop-<chart>.html` | Output file path |
| `--no-open` | false | Don't auto-open in browser |

### Chart Delivery (always do both)

After running `chart.py`, the script prints the output file path to stdout. Always:
1. **Attach the HTML file to the Telegram message** — so remote users get it instantly
2. **Auto-open in browser** (default, unless `--no-open`) — so local users get it immediately

This means both local and remote users are covered without any configuration. The file is self-contained, static, and safe to share — no credentials or API calls embedded.

---

## Experiment Tracking (`scripts/experiment.py`)

Define, monitor, and evaluate personal health experiments. Data stored in `~/.config/whoop-skill/experiments.json`.

### Supported Metrics

`hrv`, `recovery`, `sleep_performance`, `rhr`, `strain`

### Commands

#### Plan a new experiment
```bash
python3 scripts/experiment.py plan \
  --name "No alcohol for 30 days" \
  --hypothesis "HRV will increase 10%+ from baseline" \
  --start 2026-03-01 \
  --end 2026-03-31 \
  --metrics hrv,recovery,sleep_performance
```

Baseline is auto-captured from the 14 days before `--start`. Override manually:
```bash
python3 scripts/experiment.py plan \
  --name "Cold plunge experiment" \
  --hypothesis "RHR will drop 3+ bpm" \
  --start 2026-03-10 --end 2026-04-10 \
  --metrics hrv,rhr \
  --baseline-hrv 45.0 \
  --baseline-rhr 58
```

#### Plan with post-workout segmentation

Use `--segment-workouts` when your hypothesis is specifically about recovery *after training sessions* rather than overall daily averages. The tracker will fetch your workout history, identify qualifying sessions, and measure recovery metrics only in the 24–48h window after each workout.

```bash
python3 scripts/experiment.py plan \
  --name "My supplement experiment" \
  --hypothesis "Post-strength recovery improves 10%+ vs baseline" \
  --start YYYY-MM-DD --end YYYY-MM-DD \
  --metrics hrv,recovery,rhr \
  --segment-workouts \
  --min-strain 5
```

Flags:
- `--segment-workouts` — enables post-workout segmentation mode
- `--min-strain <float>` — minimum workout strain to qualify (default: 5.0). Filters out light activity like walking or yoga.
- `--days-after <range>` — recovery window to measure, e.g. `1-2` (days 1 and 2 after workout) or `1` (next day only). Default: `1-2`

When segmentation is on, `status` and `report` show **two views**: overall rolling averages (all days) and post-workout recovery (only the days after qualifying workouts). The verdict is evaluated against the post-workout view.

The post-workout baseline is also segmented — auto-captured from qualifying workouts in the 14 days before `--start` — so the comparison is apples-to-apples.

#### Add segmentation to an existing experiment
```bash
python3 scripts/experiment.py add-segmentation \
  --id <id> \
  --min-strain 5 \
  --days-after 1-2
```

Patches a previously created experiment to add post-workout segmentation and recomputes the post-workout baseline from the original baseline window.

#### List experiments
```bash
python3 scripts/experiment.py list
```

#### Check status (mid-experiment)
```bash
python3 scripts/experiment.py status --id <id>
```
Shows current averages vs baseline with % change and trend arrows. If segmentation is enabled, shows both overall and post-workout views with a per-workout breakdown.

#### Final report
```bash
python3 scripts/experiment.py report --id <id>
```
Full before/after comparison, verdict (met / partially met / not met / inconclusive), plain-language summary. Verdict is evaluated on post-workout data when segmentation is on.

---

## Obsidian Logging (`scripts/log_to_obsidian.py`) *(optional)*

> **This feature is entirely optional.** If you don't use Obsidian, skip this section — the rest of the skill works without it. To enable it, set `vault_path` in `~/.config/whoop-skill/config.json` to your Obsidian vault directory. The script will not run if no vault is configured.

> **Note:** `git` is declared as a dependency because the script calls git commands, but it is only ever invoked if your Obsidian vault is a git repository. If the vault directory has no `.git` folder, the script detects this, writes the daily note, and skips all git commands — no errors, no git required in practice.

Appends today's WHOOP stats to the Obsidian daily note at:
`<vault_path>/Daily Notes/YYYY-MM-DD.md` (configured via `vault_path` in `~/.config/whoop-skill/config.json`)

After writing, commits and pushes the vault (`git add -A && git commit && git push`).

### Usage

```bash
# Log today
python3 scripts/log_to_obsidian.py

# Backfill a specific date
python3 scripts/log_to_obsidian.py --date 2026-03-01

# Preview without writing
python3 scripts/log_to_obsidian.py --dry-run
```

### Output format in daily note

```markdown
## 🏋️ WHOOP

| Metric | Value |
|--------|-------|
| Recovery | 82% 💚 |
| HRV | 54ms |
| Resting HR | 58 bpm |
| Sleep Performance | 91% |
| Sleep Duration | 7h 42m |
| Day Strain | 8.4 |

_Logged by Assistant at 7:15 AM ET_
```

- Creates the daily note if it doesn't exist
- Skips silently if the WHOOP section already exists
- Idempotent — safe to run multiple times

---

## Morning Brief Integration

Add the following snippet to `HEARTBEAT.md` to include WHOOP recovery + HRV in morning briefs.

```markdown
## 🏋️ WHOOP Morning Check

Run on heartbeats between 06:00–10:00 ET:

1. Run: `python3 scripts/fetch.py /recovery --limit 1`
2. Extract `records[0].score.recovery_score` and `records[0].score.hrv_rmssd_milli`
3. Include in morning message:

   > 🏋️ **WHOOP** — Recovery: {score}% {emoji} | HRV: {hrv}ms
   > 
   > _(Green 💚 = push hard. Yellow 💛 = moderate. Red 🔴 = rest day.)_

4. If recovery < 34 (red), mention it proactively even if the user hasn't asked.
5. If Obsidian logging is configured, also run: `python3 scripts/log_to_obsidian.py`
```

**Copy-paste ready HEARTBEAT.md snippet:**

```markdown
### WHOOP (run once, 06:00–10:00 ET)
- Fetch recovery: `python3 scripts/fetch.py /recovery --limit 1`
- Parse recovery_score + hrv_rmssd_milli from records[0].score
- Report: "🏋️ Recovery: {score}% | HRV: {hrv}ms" (add 💚/💛/🔴 based on score ≥67 / ≥34 / <34)
- If red recovery, mention proactively
- Log to Obsidian (if configured): `python3 scripts/log_to_obsidian.py`
```

---

## Health Interpretation

See `references/health_analysis.md` for a science-backed guide covering:
- HRV (RMSSD) ranges by age, what trends mean, red flags
- Resting heart rate interpretation by fitness level
- Sleep stage breakdown (deep/REM/light targets, deficit consequences)
- Recovery score zones (green/yellow/red) and recommended actions
- Strain scale and how to match strain to recovery
- SpO2 and skin temperature context
- Overtraining pattern recognition
- When to see a doctor

---

## References

- `references/api.md` — Full WHOOP API endpoint reference
- `references/health_analysis.md` — Health metric interpretation guide
- WHOOP Developer Dashboard: https://developer-dashboard.whoop.com
- WHOOP API docs: https://developer.whoop.com/api
