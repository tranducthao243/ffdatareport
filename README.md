# ffdatareport

`ffdatareport` đang được nâng cấp thành **Data Master v1** cho Seatalk reporting.

Mục tiêu của repo:

- giữ nguyên fetch engine từ Social Data
- chuẩn hóa raw CSV thành dữ liệu ổn định hơn
- phân tích nhiều loại báo cáo từ cùng một dataset
- gửi nhiều gói báo cáo khác nhau tới nhiều group Seatalk theo config

## Kiến trúc phase 1

Phase 1 giữ fetch engine hiện tại và thêm một lớp dữ liệu ở sau fetch:

```text
Social Data fetch CSV
-> normalize/store (SQLite)
-> analyze (TOPA-TOPF)
-> report builders (SO1, SO2, TOPD, TOPF)
-> seatalk payload + sender
```

Các module mới:

- [normalize/store.py](C:/Users/admin/OneDrive/Documents/New%20project/datatool/normalize/store.py)
- [analyze/](C:/Users/admin/OneDrive/Documents/New%20project/datatool/analyze)
- [report/](C:/Users/admin/OneDrive/Documents/New%20project/datatool/report)
- [seatalk/](C:/Users/admin/OneDrive/Documents/New%20project/datatool/seatalk)
- [app/pipeline.py](C:/Users/admin/OneDrive/Documents/New%20project/datatool/app/pipeline.py)
- [config/groups.json](C:/Users/admin/OneDrive/Documents/New%20project/datatool/config/groups.json)
- [config/reports.json](C:/Users/admin/OneDrive/Documents/New%20project/datatool/config/reports.json)
- [config/campaigns.json](C:/Users/admin/OneDrive/Documents/New%20project/datatool/config/campaigns.json)

Fetch engine cũ vẫn ở:

- [datasocial/fetcher.py](C:/Users/admin/OneDrive/Documents/New%20project/datatool/datasocial/fetcher.py)
- [datasocial/exporter.py](C:/Users/admin/OneDrive/Documents/New%20project/datatool/datasocial/exporter.py)
- [datasocial/cli.py](C:/Users/admin/OneDrive/Documents/New%20project/datatool/datasocial/cli.py)

## Dữ liệu phase 1

Business scope mặc định:

- KOL categories: `14, 22, 23, 24`
- Official category: `13`
- KOL platforms: TikTok, YouTube
- Official platforms: TikTok, YouTube, Facebook
- whitelist hashtag KOL:
  - `freefire`
  - `nhasangtaofreefire`
  - `ff`
  - `garena`

Preset fetch mới cho Data Master:

- [presets/ffvn_master_daily.json](C:/Users/admin/OneDrive/Documents/New%20project/datatool/presets/ffvn_master_daily.json)

Preset này fetch rộng hơn preset daily cũ để đủ dữ liệu cho:

- KOL report
- campaign report
- official report

## Analyzer codes

- `TOPA`: Top 5 TikTok + YouTube video nhiều view nhất trong rolling 1-2 ngày, có whitelist hashtag
- `TOPB`: Top 5 TikTok + YouTube video nhiều view nhất trong 7 ngày, có whitelist hashtag
- `TOPC`: Top 5 KOL channels 7 ngày theo total view
- `TOPD`: Báo cáo campaign theo `config/campaigns.json`
- `TOPE`: Tổng view + tổng clip toàn bộ KOL content 7 ngày
- `TOPF`: Báo cáo official category `13`

## Report packages

- `SO1`: `TOPA + TOPB + TOPC + TOPE`
- `SO2`: `TOPA + TOPB + TOPC`
- `TOPD_REPORT`: package campaign
- `TOPF_REPORT`: package official

## Local commands

### 1. Fetch raw CSV bằng engine hiện tại

```powershell
python -m datasocial --preset ffvn_master_daily --fetch-only
```

### 2. Build SQLite normalized store từ CSV

```powershell
python -m datasocial --build-master-store --load-export outputs\ffvn_master_latest.csv --save-store outputs\ffvn_master.sqlite
```

### 3. Build config-driven report packages từ SQLite

```powershell
python -m datasocial --build-configured-reports --load-store outputs\ffvn_master.sqlite --save-report outputs\ffvn_master_reports.json
```

### 4. Build và gửi nhiều package qua Seatalk theo config

```powershell
python -m datasocial --build-configured-reports --load-store outputs\ffvn_master.sqlite --save-report outputs\ffvn_master_reports.json --send-seatalk
```

### 5. Build preview text cho từng group mà không gửi thật

```powershell
python -m datasocial --build-configured-reports --load-store outputs\ffvn_master.sqlite --save-report outputs\ffvn_master_reports.json --save-rendered-dir outputs\rendered_reports
```

## GitHub Actions

Workflow production vẫn giữ cấu trúc cũ:

- [ffvn-daily-fetch.yml](C:/Users/admin/OneDrive/Documents/New%20project/datatool/.github/workflows/ffvn-daily-fetch.yml)
- [ffvn-daily-send.yml](C:/Users/admin/OneDrive/Documents/New%20project/datatool/.github/workflows/ffvn-daily-send.yml)
- [ffvn-daily-publish-data.yml](C:/Users/admin/OneDrive/Documents/New%20project/datatool/.github/workflows/ffvn-daily-publish-data.yml)

Production model hiện tại:

- App Script làm scheduler
- GitHub Actions làm executor
- fetch workflow tạo:
  - `outputs/ffvn_master_latest.csv`
  - `outputs/ffvn_master.sqlite`
- send workflow đọc SQLite và gửi report package theo config
- send workflow cũng có thể chạy ở chế độ preview-only để chỉ build artifact mà không gửi SeaTalk

## Required secrets

- `DATASOCIAL_USESSION`
- `SEATALK_APP_ID`
- `SEATALK_APP_SECRET`
- `SEATALK_GROUP_ID`

Optional nếu tách thêm group:

- `SEATALK_CAMPAIGN_GROUP_ID`
- `SEATALK_OFFICIAL_GROUP_ID`

## Test

```powershell
python -m unittest tests.test_datasocial_parser tests.test_datasocial_analysis tests.test_datasocial_exporter tests.test_datasocial_seatalk tests.test_datasocial_presets tests.test_datamaster_phase1
python -m datasocial --help
```
