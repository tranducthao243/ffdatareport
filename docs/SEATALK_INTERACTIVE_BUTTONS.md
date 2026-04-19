# Seatalk Interactive Buttons

`SO1` hien tai duoc gui theo cach on dinh hon voi Seatalk:

- bao cao tong = text message nhu cu
- card nut = mot `interactive_message` ngan ngay sau do
- `button_group` = `Data Campaign`, `Official Channel`

Day la cach thuc te hon vi card ngan de duoc Seatalk chap nhan on dinh.

## Callback runtime

Repo hien tai da co callback runtime toi gian, va co the deploy len Railway:

```powershell
python -m seatalk.callback_server --db-path outputs\ffvn_master.sqlite --preset ffvn_master_daily
```

Runtime nay:

1. nhan callback `interactive_message_click`
2. doc `callbackPayload`
3. xac dinh `target_report_code`
4. neu can, tu dong dong bo `ffvn_master.sqlite` moi nhat tu GitHub artifact
5. build lai `TOPD_REPORT` hoac `TOPF_REPORT` tu SQLite + config hien tai
6. gui private message tra ve cho nguoi bam

## Cac bien moi truong quan trong

- `SEATALK_APP_ID`
- `SEATALK_APP_SECRET`
- `SEATALK_SIGNING_SECRET` (optional)
- `SEATALK_VERIFY_SIGNATURE=true|false`
- `DATAMASTER_STORE_PATH` (optional, mac dinh `outputs/ffvn_master.sqlite`)
- `DATASOCIAL_CALLBACK_PRESET` (optional, mac dinh `ffvn_master_daily`)
- `GITHUB_TOKEN`
- `GITHUB_REPOSITORY`
- `DATAMASTER_ARTIFACT_NAME`
- `DATAMASTER_SYNC_ON_START=true|false`
- `DATAMASTER_SYNC_ON_CLICK=true|false`

## Luu y

- GitHub Actions khong the tu dung lam callback runtime vi khong co HTTP endpoint song lien tuc.
- De nut bam hoat dong that, callback URL cua Seatalk phai tro vao service public tren Railway tai duong dan `/callback`.
