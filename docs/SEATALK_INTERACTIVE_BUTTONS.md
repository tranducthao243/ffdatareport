# Seatalk Interactive Buttons

Phần này là groundwork cho interactive bot, chưa phải callback runtime hoàn chỉnh.

## Hiện đã có trong repo

- `SO1` package sẽ sinh ra `interactiveActions` trong JSON output
- mỗi action có:
  - `label`
  - `actionType`
  - `targetReportCode`
  - `callbackPayload`
- preview artifact `.txt` sẽ ghi kèm các action này để operator kiểm tra

Hiện tại action mặc định của `SO1`:

- `Data Campaign` -> `TOPD_REPORT`
- `Official Channel` -> `TOPF_REPORT`

## Chưa làm ở bước này

- chưa gửi button thật lên SeaTalk
- chưa có callback endpoint public
- chưa verify signature callback từ SeaTalk
- chưa có logic reply khi user bấm button

## Callback runtime cần có ở bước sau

SeaTalk interactive flow cần một server/webhook luôn online:

1. SeaTalk gửi event về callback endpoint
2. server verify signature
3. parse `interactive_message_click`
4. đọc `callbackPayload`
5. build report mục tiêu (`TOPD_REPORT` hoặc `TOPF_REPORT`)
6. gửi tin nhắn follow-up qua SeaTalk API

## Gợi ý runtime phù hợp

- Apps Script webhook
- Cloud Run
- Render / Railway
- VPS nhỏ

GitHub Actions không phù hợp để làm callback runtime vì không có endpoint sống liên tục.
