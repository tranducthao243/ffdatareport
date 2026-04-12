# GitHub Deployment Guide

This project is designed to run safely on GitHub by using GitHub's own authentication and permission model instead of a custom login page.

## Recommended operating model

- Keep the repository **private**
- Use the **Actions** tab as the control panel
- Use a protected GitHub **Environment** for production secrets
- Let GitHub account login be the only UI login layer

This is safer and simpler than building a custom web login in front of a tool that already depends on sensitive private cookies and bot secrets.

## What the GitHub interface looks like

You now have two workflows:
You now have four workflows:

- `.github/workflows/ffvn-daily-fetch.yml`
  - scheduled fetch-only job
  - prepares the CSV artifact before the send window
- `.github/workflows/ffvn-daily-send.yml`
  - scheduled send-only job
  - downloads the latest fetch artifact and sends the report to SeaTalk
- `.github/workflows/ffvn-manual-control.yml`
  - manual control panel with form inputs
  - lets you choose:
    - send SeaTalk or not
    - fetch window (`1D`, `4D`, `7D`, `30D`)
    - report mode (`complete_previous_day`, `today_so_far`)
    - timeout
    - SeaTalk title
- `.github/workflows/seatalk-test-ping.yml`
  - instant SeaTalk delivery test
  - sends a simple message without fetching Social Data

The manual workflow form in the Actions tab is the intended "online control interface".

## Why there is no separate GitHub login page

GitHub Pages does not provide a strong built-in auth layer suitable for secrets-backed operations.

For this tool, the safer pattern is:

- private repo
- GitHub login required to access the repo
- Actions tab as the operator UI
- protected Environment for production secrets
- optional required reviewers before a production job can read secrets

## Setup steps

### 1. Create a private GitHub repository

Push the repo to a private repository. Do not make it public because it relies on:

- `DATASOCIAL_USESSION`
- `SEATALK_APP_SECRET`

### 2. Create a GitHub Environment

Create an environment named:

- `ffvn-reporting`

Recommended settings:

- add required reviewers for manual approval before production runs
- keep environment secrets only in this environment

### 3. Add environment secrets

Add these secrets to the `ffvn-reporting` environment:

- `DATASOCIAL_USESSION`
- `SEATALK_APP_ID`
- `SEATALK_APP_SECRET`
- `SEATALK_GROUP_ID`

Optional repo-level variables:

- `DATASOCIAL_TIMEOUT`

### 4. Enable Actions

In the repository:

- enable GitHub Actions
- verify the two workflows appear in the Actions tab

### 5. Test the manual control workflow

Run:

- `FFVN Report Control Panel`

Suggested first test:

- `send_seatalk = false`
- `fetch_window = 1D`
- `report_mode = complete_previous_day`
- `timeout_seconds = 300`

Then inspect:

- workflow logs
- uploaded artifacts
- job summary in GitHub Actions

### 6. Test SeaTalk delivery

Run the same manual workflow with:

- `send_seatalk = true`

Verify the report reaches the SeaTalk group.

### 7. Turn on the schedule

The fetch workflow currently runs at:

- `02:30 UTC`
- equivalent to `09:30` in Vietnam when offset is `UTC+7`

The send workflow currently runs at:

- `03:30 UTC`
- equivalent to `10:30` in Vietnam when offset is `UTC+7`

The weekly workflow currently runs at:

- `02:10 UTC` every Monday
- equivalent to `09:10` in Vietnam every Monday when offset is `UTC+7`

If you want a different time, edit the cron in:

- `.github/workflows/ffvn-daily-report.yml`

## Operational caveats

### Social Data auth is still session-based

`DATASOCIAL_USESSION` is a browser-style session cookie.

That means:

- it can expire
- it can rotate
- a scheduled run will fail if the stored cookie is stale

Operationally, treat it as a rotating secret, not a permanent API token.

### GitHub schedule is fixed in workflow YAML

If you want to change the automatic timings, edit the cron expressions in the fetch/send workflows and commit the change.

GitHub Actions does not support a 1-minute cron for normal scheduled workflows. In practice:

- use `SeaTalk Test Ping` for immediate delivery tests
- use the manual control workflow for real report tests
- if you really need a scheduled test loop, the practical minimum on GitHub-hosted runners is every 5 minutes

### Manual workflow is the main operator interface

Use the manual workflow when you need to:

- run a one-off report
- test a smaller window
- disable SeaTalk while validating data
- rerun after updating secrets

### Fastest way to test bot delivery

Use:

- `SeaTalk Test Ping`

This bypasses Social Data fetch completely and verifies only:

- SeaTalk app auth
- target group routing
- message delivery

### Production timing model

The production daily flow is now split into two stages:

1. `FFVN Daily Fetch (Scheduled)`
   - target time: `09:30` Vietnam time
   - fetches Social Data
   - stores `outputs/ffvn_daily_latest.csv` as a GitHub artifact

2. `FFVN Daily Send (Scheduled)`
   - target time: `10:30` Vietnam time
   - downloads the latest fetch artifact
   - runs `analyze-only`
   - sends the report to SeaTalk

This avoids delayed sends when the Social Data fetch takes several minutes.

## Recommended next hardening steps

- add retry per export chunk
- log failed chunks into the report artifact
- optionally create a second workflow for weekly/monthly reports
- later add campaign-specific inputs after the UI phase
