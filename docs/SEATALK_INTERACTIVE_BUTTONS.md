# Seatalk Interactive Buttons

`SO1` hien tai duoc gui bang mot `interactive_message` duy nhat:

- `title` = tieu de report tong
- `description` = noi dung report
- `button_group` = `Data Campaign`, `Official Channel`

Nhu vay nut se nam cung message bao cao, thay vi mot follow-up card tach rieng.

## Callback runtime

Repo hien tai da co callback runtime toi gian:

```powershell
python -m seatalk.callback_server --db-path outputs\ffvn_master.sqlite --preset ffvn_master_daily
```

Runtime nay:

1. nhan callback `interactive_message_click`
2. doc `callbackPayload`
3. xac dinh `target_report_code`
4. build lai `TOPD_REPORT` hoac `TOPF_REPORT` tu SQLite + config hien tai
5. gui private message tra ve cho nguoi bam

## Cac bien moi truong quan trong

- `SEATALK_APP_ID`
- `SEATALK_APP_SECRET`
- `SEATALK_SIGNING_SECRET` (optional)
- `SEATALK_VERIFY_SIGNATURE=true|false`
- `DATAMASTER_STORE_PATH` (optional, mac dinh `outputs/ffvn_master.sqlite`)
- `DATASOCIAL_CALLBACK_PRESET` (optional, mac dinh `ffvn_master_daily`)

## Luu y

- GitHub Actions khong the tu dung lam callback runtime vi khong co HTTP endpoint song lien tuc.
- De nut bam hoat dong that, callback URL cua Seatalk phai tro vao mot process dang chay `seatalk.callback_server` hoac mot runtime tuong duong.
