# Datasocial

`datasocial` is a private reporting pipeline for Garena Social Data:

- fetches export data from the private GraphQL backend
- normalizes rows into a reporting model
- builds modular FFVN KOL reports
- sends compact summaries to SeaTalk

## Core layers

- [datasocial/fetcher.py](C:/Users/admin/OneDrive/Documents/datatool/datasocial/fetcher.py): GraphQL session + export fetch
- [datasocial/normalize.py](C:/Users/admin/OneDrive/Documents/datatool/datasocial/normalize.py): export row normalization
- [datasocial/report_engine.py](C:/Users/admin/OneDrive/Documents/datatool/datasocial/report_engine.py): modular analytics engine
- [datasocial/formatter.py](C:/Users/admin/OneDrive/Documents/datatool/datasocial/formatter.py): console + SeaTalk formatting
- [datasocial/seatalk.py](C:/Users/admin/OneDrive/Documents/datatool/datasocial/seatalk.py): SeaTalk auth and delivery
- [datasocial/cli.py](C:/Users/admin/OneDrive/Documents/datatool/datasocial/cli.py): CLI orchestration
- [presets/ffvn_daily.json](C:/Users/admin/OneDrive/Documents/datatool/presets/ffvn_daily.json): FFVN daily preset
- [presets/ffvn_weekly.json](C:/Users/admin/OneDrive/Documents/datatool/presets/ffvn_weekly.json): FFVN weekly preset

## Setup

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

## Test

```powershell
python -m unittest tests.test_datasocial_parser tests.test_datasocial_analysis tests.test_datasocial_exporter tests.test_datasocial_seatalk
python -m datasocial --help
```

## Daily FFVN preset

The FFVN preset already includes:

- app: `ffvn`
- export flow
- split fetch by category and day
- tracked categories: `14, 22, 23, 24`
- tracked platforms: `0, 2`
- hashtags: `#freefire`, `#nhasangtaofreefire`
- event tags kept as future campaign metadata
- report mode: `complete_previous_day`
- timezone: `Asia/Ho_Chi_Minh`
- default output files:
  - `outputs/ffvn_daily_latest.csv`
  - `outputs/ffvn_daily_latest.json`

### Short daily command

```powershell
python -m datasocial --preset ffvn_daily --send-seatalk
```

Equivalent local script:

```powershell
.\scripts\run_ffvn_daily.ps1
```

## Analyze an existing export

```powershell
python -m datasocial --preset ffvn_daily --analyze-only --load-export outputs\export_chunked.csv
```

## Dynamic windows

If you do not pass explicit dates, `datasocial` computes them automatically in `Asia/Ho_Chi_Minh`.

Supported fetch windows:

- `1D`
- `4D`
- `7D`
- `30D`

Supported modes:

- `complete_previous_day`
- `today_so_far`

Example:

```powershell
python -m datasocial --preset ffvn_daily --fetch-window 30D --report-mode today_so_far --send-seatalk
```

## GitHub Actions

Workflow scaffold:

- [.github/workflows/ffvn-daily-report.yml](C:/Users/admin/OneDrive/Documents/datatool/.github/workflows/ffvn-daily-report.yml)
- [.github/workflows/ffvn-weekly-report.yml](C:/Users/admin/OneDrive/Documents/datatool/.github/workflows/ffvn-weekly-report.yml)
- [.github/workflows/ffvn-manual-control.yml](C:/Users/admin/OneDrive/Documents/datatool/.github/workflows/ffvn-manual-control.yml)
- [docs/GITHUB_DEPLOYMENT.md](C:/Users/admin/OneDrive/Documents/datatool/docs/GITHUB_DEPLOYMENT.md)

Required GitHub Secrets:

- `DATASOCIAL_USESSION`
- `SEATALK_APP_ID`
- `SEATALK_APP_SECRET`
- `SEATALK_GROUP_ID`

Default schedule in the scaffold:

- `02:10 UTC`
- equivalent to `09:10` in Vietnam when offset is `UTC+7`

Recommended production setup:

- private GitHub repo
- Actions tab as the operator interface
- `ffvn-reporting` GitHub Environment for production secrets
- use the manual control workflow for one-off runs
- use the scheduled daily workflow for the daily send
- use the scheduled weekly workflow for the weekly send

## Notes

- Social Data still relies on a valid `usession` cookie.
- SeaTalk delivery is already working for group delivery.
- Campaign KPI tracking is intentionally left as a future module after the GitHub/UI phase.
