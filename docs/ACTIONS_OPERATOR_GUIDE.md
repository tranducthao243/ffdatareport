# HƯỚNG DẪN VẬN HÀNH GITHUB ACTIONS

Tài liệu này dành cho người vận hành tool `datasocial` trên GitHub.

## 1. Tool đang chạy theo mô hình nào

Hiện nay scheduler chính **không còn nằm trong GitHub cron**.

Mô hình production hiện tại là:

1. Google Apps Script gọi workflow fetch trên GitHub.
2. Workflow fetch lấy dữ liệu từ Social Data và lưu artifact CSV.
3. Google Apps Script gọi workflow send trên GitHub.
4. Workflow send đọc artifact fetch, build report từ SQLite và gửi SeaTalk.

Project Apps Script đang dùng:

- `push_repo_ffdatareport`

## 2. Các workflow chính trên GitHub

### `FFVN Daily Fetch (Scheduled)`

Mục đích:

- lấy dữ liệu từ Social Data
- lưu file CSV thành artifact

Lưu ý:

- workflow này hiện được gọi bằng `workflow_dispatch`
- Apps Script là thành phần quyết định giờ chạy thực tế

Output:

- `outputs/ffvn_daily_latest.csv`
- artifact tên `ffvn-daily-fetch-latest`

### `FFVN Daily Send (Scheduled)`

Mục đích:

- tải artifact fetch mới nhất
- dựng SQLite nếu cần
- build report package theo config
- gửi report qua SeaTalk hoặc chỉ build preview

Lưu ý:

- workflow này hiện được gọi bằng `workflow_dispatch`
- Apps Script là thành phần quyết định giờ chạy thực tế

Output:

- `outputs/ffvn_master_reports.json`
- `outputs/rendered_reports/*.txt`
- artifact tên `ffvn-daily-send-latest`

### `FFVN Report Control Panel`

Mục đích:

- chạy tay khi cần
- test report
- test gửi SeaTalk
- rerun thủ công

Những gì chọn trong form của workflow này chỉ áp dụng cho **lần chạy đó**, không lưu thành cấu hình production.

### `SeaTalk Test Ping`

Mục đích:

- test bot SeaTalk nhanh
- không fetch Social Data
- không build report thật

## 3. Khi nào dùng workflow nào

### Vận hành bình thường

Không cần bấm tay gì cả.

Apps Script sẽ tự gọi:

- `FFVN Daily Fetch (Scheduled)`
- `FFVN Daily Send (Scheduled)`

### Test bot nhanh nhất

Dùng:

- `SeaTalk Test Ping`

### Test report bằng tay

Dùng:

- `FFVN Report Control Panel`

Gợi ý test nhẹ:

- `send_seatalk = false`
- `fetch_window = 1D`
- `report_mode = complete_previous_day`

### Test flow production tách riêng

Chạy đúng thứ tự:

1. `FFVN Daily Fetch (Scheduled)`
2. đợi artifact fetch xuất hiện
3. `FFVN Daily Send (Scheduled)`

### Preview report mà không gửi thật

Tại `FFVN Daily Send (Scheduled)`, chọn:

- `send_mode = preview`

Kết quả:

- workflow vẫn build đầy đủ package
- vẫn upload JSON + preview text artifact
- không gọi SeaTalk API

## 4. Giờ chạy thật đang nằm ở đâu

Giờ chạy thật **nằm ở Apps Script**, không còn nằm trong cron của workflow YAML.

Nếu muốn đổi giờ:

1. mở Apps Script project `push_repo_ffdatareport`
2. sửa giờ/trigger trong Apps Script
3. lưu lại

## 5. Logic report production hiện tại

Preset production đang dùng:

- `ffvn_daily`

Thông số chính:

- `fetch_window = 7D`
- `report_mode = complete_previous_day`
- timezone: `Asia/Ho_Chi_Minh`
- category ids: `14, 22, 23, 24`
- platform ids: `0, 2`
- fetch chia theo:
  - category
  - day

Hashtag coverage hiện tại:

- `#freefire`
- `#nhasangtaofreefire`
- `#free_fire`
- `#garenafreefire`
- `#sangtaofreefire`
- `#craftland`
- `#garena`

## 6. Các phần chính trong report

- `Top Content 1D`
- `Trend Videos 7D`
- `Daily Views 7D`
- `Daily Posts 7D`
- `Top KOLs 7D`
- `Overview 7D`

Trong đó:

- `Daily Views 7D` lấy theo toàn bộ tập KOL đã fetch, không bó hashtag
- `Daily Posts 7D` lấy theo toàn bộ tập KOL đã fetch, không bó hashtag
- `Overview 7D` cũng là tổng toàn bộ tập KOL đã fetch

## 7. Secrets cần có

GitHub Environment:

- `ffvn-reporting`

Secrets bắt buộc:

- `DATASOCIAL_USESSION`
- `SEATALK_APP_ID`
- `SEATALK_APP_SECRET`
- `SEATALK_GROUP_ID`

## 8. Nếu cần cập nhật `DATASOCIAL_USESSION`

Lấy từ browser khi đang đăng nhập `socialdata.garena.vn`.

Cách làm:

1. mở website Social Data
2. đăng nhập đúng tài khoản có quyền
3. mở DevTools
4. tìm cookie `usession`
5. copy giá trị
6. cập nhật lại GitHub secret `DATASOCIAL_USESSION`

## 9. Cách đọc artifact

Sau khi workflow chạy xong:

1. mở run trên tab `Actions`
2. kéo xuống `Artifacts`
3. tải file zip
4. giải nén trên máy

Thường sẽ có:

- fetch:
  - `ffvn_daily_latest.csv`
- send:
  - `ffvn_daily_latest.json`

## 10. Các lỗi thường gặp

### Không có fetch artifact cho send

Biểu hiện:

- `No recent fetch artifact found in the last 12 hours. Run FFVN Daily Fetch (Scheduled) first.`

Ý nghĩa:

- send không tìm thấy artifact CSV mới

Fix:

- chạy fetch trước
- hoặc kiểm tra Apps Script có trigger fetch thành công không

### Fetch bị timeout

Biểu hiện:

- read timeout
- workflow chạy lâu rồi fail

Fix:

- kiểm tra `DATASOCIAL_USESSION`
- test bằng `1D` qua control panel
- kiểm tra backend Social Data

### SeaTalk gửi lỗi

Khả năng:

- sai app id/secret
- sai group id
- bot bị remove khỏi group

Fix nhanh:

- chạy `SeaTalk Test Ping`

## 11. Khi nào cần vào GitHub

Chỉ cần vào GitHub khi:

- muốn test
- muốn rerun
- muốn xem log lỗi
- muốn xem artifact
- muốn đổi wording report
- muốn cập nhật secret

Bạn **không cần** vào GitHub bấm tay hằng ngày nếu Apps Script đang trigger đúng.

## 12. Ghi nhớ ngắn gọn nhất

- `SeaTalk Test Ping` = test bot
- `FFVN Report Control Panel` = chạy tay
- `FFVN Daily Fetch (Scheduled)` = workflow fetch do Apps Script gọi
- `FFVN Daily Send (Scheduled)` = workflow send do Apps Script gọi

Và:

- scheduler chính là Apps Script
- GitHub chỉ là nơi thực thi workflow
