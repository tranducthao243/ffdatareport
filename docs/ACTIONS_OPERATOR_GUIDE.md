# Actions Operator Guide

This guide is for day-to-day operators of the GitHub version of `datasocial`.

It explains:

- what each workflow does
- when to run which workflow
- where to change schedules
- where to update secrets
- how to troubleshoot common failures

## 1. What this tool does

The tool automates FFVN reporting from the private Social Data system.

Production flow:

1. fetch data from Social Data
2. save the fetched CSV as a GitHub artifact
3. build the report from that saved CSV
4. send the report to SeaTalk

The production flow is intentionally split into two scheduled workflows:

- fetch first
- send later

This prevents delayed SeaTalk sends when Social Data fetches take a long time.

## 2. Main workflows in GitHub Actions

### `FFVN Daily Fetch (Scheduled)`

Purpose:

- fetch Social Data before the send window
- save the CSV artifact

Current target time:

- `09:00` Asia/Ho_Chi_Minh

What it produces:

- `outputs/ffvn_daily_latest.csv`
- uploaded to GitHub as an artifact

### `FFVN Daily Send (Scheduled)`

Purpose:

- download the latest fetch artifact
- analyze it
- send the report to SeaTalk

Current target time:

- `09:50` Asia/Ho_Chi_Minh

What it produces:

- `outputs/ffvn_daily_latest.json`
- sends the final message to the configured SeaTalk group

### `FFVN Report Control Panel`

Purpose:

- manual one-off run
- useful for testing
- can run with or without SeaTalk delivery

Use this when:

- you want to test a smaller window
- you want to rerun manually
- you want to validate a config change

### `SeaTalk Test Ping`

Purpose:

- test only the SeaTalk bot delivery
- does **not** fetch Social Data

Use this when:

- you only want to verify bot credentials and group delivery
- you do not want to wait for Social Data fetch

## 3. Which workflow should I use?

### Daily production

Use:

- `FFVN Daily Fetch (Scheduled)`
- `FFVN Daily Send (Scheduled)`

Do not run both manually every day. GitHub schedule handles that automatically.

### Quick bot test

Use:

- `SeaTalk Test Ping`

### Manual report test

Use:

- `FFVN Report Control Panel`

Suggested test settings:

- `send_seatalk = false`
- `fetch_window = 1D`
- `report_mode = complete_previous_day`

Then, when that works:

- rerun with `send_seatalk = true`

## 4. How the production schedule works

Current daily production timing:

- `09:00` Vietnam time: fetch data
- `09:50` Vietnam time: send report

Why split it:

- Social Data fetch can take many minutes
- SeaTalk delivery should still happen at a predictable time

## 5. Where to change schedules

### Fetch schedule

File:

- `.github/workflows/ffvn-daily-fetch.yml`

Current cron:

- `0 2 * * *`

Meaning:

- `02:00 UTC`
- `09:00` Vietnam time

### Send schedule

File:

- `.github/workflows/ffvn-daily-send.yml`

Current cron:

- `50 2 * * *`

Meaning:

- `02:50 UTC`
- `09:50` Vietnam time

If you want to change the automatic time:

1. edit the cron in the workflow file
2. commit the change
3. push to `main`

## 6. Where to change report behavior

### Preset defaults

File:

- `presets/ffvn_daily.json`

Use this file to change:

- tracked categories
- tracked platforms
- hashtag filters
- event hashtags
- top limits
- trend minimum views
- default SeaTalk title

### Report wording and message formatting

Files:

- `datasocial/formatter.py`
- `datasocial/report_engine.py`

Use these files to change:

- report section titles
- SeaTalk wording
- compact formatting
- ranking block display
- overall report structure

## 7. Where to update secrets

GitHub path:

- `Settings -> Environments -> ffvn-reporting`

Required secrets:

- `DATASOCIAL_USESSION`
- `SEATALK_APP_ID`
- `SEATALK_APP_SECRET`
- `SEATALK_GROUP_ID`

## 8. How to refresh `DATASOCIAL_USESSION`

`DATASOCIAL_USESSION` comes from the Social Data website session cookie.

Get it from the browser:

1. open `socialdata.garena.vn`
2. log in with the working account
3. open browser devtools
4. go to cookies or a GraphQL request
5. copy the current `usession` value
6. replace the GitHub Environment secret `DATASOCIAL_USESSION`

If this cookie expires, scheduled fetches will fail.

## 9. How to read artifacts

After a workflow run succeeds:

1. open the workflow run page
2. scroll to the `Artifacts` section
3. download the artifact zip
4. extract it locally

Common outputs:

- fetch workflow:
  - `ffvn_daily_latest.csv`
- send/analyze workflow:
  - `ffvn_daily_latest.json`

## 10. How to troubleshoot

### Case A: fetch workflow runs for a long time

This usually means Social Data is slow.

Check:

- the `Run FFVN daily fetch` step log

Remember:

- fetch workflow has a hard timeout
- it will not run forever

### Case B: fetch workflow fails with timeout

Common error:

- `Read timed out`

Possible fixes:

- increase timeout
- reduce fetch window in manual tests
- refresh `DATASOCIAL_USESSION`

### Case C: send workflow fails before SeaTalk

Possible cause:

- fetch artifact was not available

Fix:

- verify the fetch workflow succeeded earlier that day
- rerun fetch manually
- rerun send after fetch succeeds

### Case D: SeaTalk send fails

Possible causes:

- wrong `SEATALK_APP_ID`
- wrong `SEATALK_APP_SECRET`
- wrong `SEATALK_GROUP_ID`
- bot removed from target group

Best first test:

- run `SeaTalk Test Ping`

### Case E: report wording needs to change

Edit:

- `datasocial/formatter.py`

Then:

1. commit
2. push
3. run `FFVN Report Control Panel`

## 11. What is safe to change vs what is not

Safe for most operators:

- rerun a workflow
- use the control panel with smaller windows
- update secrets
- run SeaTalk ping

Only edit with care:

- workflow cron schedules
- preset category/platform filters
- report engine logic

## 12. Recommended routine

### Normal daily operation

Do nothing.

GitHub should:

- fetch at `09:00`
- send at `09:50`

### If something looks wrong

1. check `FFVN Daily Fetch (Scheduled)`
2. check `FFVN Daily Send (Scheduled)`
3. run `SeaTalk Test Ping`
4. if needed, run `FFVN Report Control Panel`

## 13. Important limitation

This tool still depends on:

- a valid Social Data browser session cookie

It is not yet using a permanent service account or official API token.

That means:

- if `DATASOCIAL_USESSION` expires
- or the account loses access

the fetch workflow will fail until the secret is refreshed.
