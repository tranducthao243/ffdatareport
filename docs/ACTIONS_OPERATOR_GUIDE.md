# Hướng Dẫn Vận Hành GitHub Actions

Tài liệu này dành cho người vận hành tool `datasocial` trên GitHub.

Mục tiêu của tài liệu:

- giải thích từng workflow dùng để làm gì
- khi nào dùng workflow nào
- chỗ nào để sửa giờ chạy
- chỗ nào để cập nhật secrets
- cách xử lý các lỗi thường gặp

## 1. Tool này đang làm gì

Tool này tự động tạo báo cáo FFVN từ hệ thống Social Data private của công ty.

Flow production hiện tại:

1. lấy dữ liệu từ Social Data
2. lưu file CSV đã fetch thành artifact trên GitHub
3. build report từ file CSV đó
4. gửi report sang SeaTalk

Flow production được tách thành hai workflow riêng:

- fetch trước
- send sau

Mục đích là để nếu bước fetch lâu thì vẫn không làm lệch giờ gửi SeaTalk.

## 2. Các workflow chính trên GitHub Actions

### `FFVN Daily Fetch (Scheduled)`

Mục đích:

- lấy dữ liệu từ Social Data trước giờ gửi
- lưu artifact CSV

Giờ chạy hiện tại:

- `09:00` giờ Việt Nam

Output chính:

- `outputs/ffvn_daily_latest.csv`
- file này được upload thành artifact trên GitHub

### `FFVN Daily Send (Scheduled)`

Mục đích:

- tải artifact fetch mới nhất
- phân tích dữ liệu
- gửi report sang SeaTalk

Giờ chạy hiện tại:

- `09:50` giờ Việt Nam

Output chính:

- `outputs/ffvn_daily_latest.json`
- gửi tin nhắn report vào group SeaTalk đã cấu hình

### `FFVN Report Control Panel`

Mục đích:

- chạy tay khi cần
- dùng để test
- có thể chạy có hoặc không gửi SeaTalk

Dùng workflow này khi:

- muốn test nhanh
- muốn chạy lại thủ công
- muốn thử cửa sổ nhỏ như `1D`
- muốn xác nhận thay đổi trước khi để auto chạy

### `SeaTalk Test Ping`

Mục đích:

- test riêng bot SeaTalk
- không gọi Social Data

Dùng workflow này khi:

- chỉ muốn kiểm tra bot có gửi vào group được không
- không muốn chờ bước fetch data

## 3. Khi nào nên dùng workflow nào

### Chạy production hằng ngày

Để GitHub tự chạy:

- `FFVN Daily Fetch (Scheduled)`
- `FFVN Daily Send (Scheduled)`

Không cần bấm tay mỗi ngày.

### Test bot SeaTalk nhanh nhất

Dùng:

- `SeaTalk Test Ping`

### Test report bằng tay

Dùng:

- `FFVN Report Control Panel`

Thiết lập test gợi ý:

- `send_seatalk = false`
- `fetch_window = 1D`
- `report_mode = complete_previous_day`

Khi bước này ổn, có thể chạy lại với:

- `send_seatalk = true`

## 4. Lịch production đang chạy thế nào

Lịch production hiện tại:

- `09:00` giờ Việt Nam: fetch dữ liệu
- `09:50` giờ Việt Nam: gửi report

Vì sao tách làm 2 workflow:

- fetch từ Social Data có thể mất nhiều phút
- report vẫn cần gửi vào một khung giờ cố định

## 5. Chỗ sửa giờ chạy

### Sửa giờ fetch

File:

- `.github/workflows/ffvn-daily-fetch.yml`

Cron hiện tại:

- `0 2 * * *`

Ý nghĩa:

- `02:00 UTC`
- `09:00` giờ Việt Nam

### Sửa giờ send

File:

- `.github/workflows/ffvn-daily-send.yml`

Cron hiện tại:

- `50 2 * * *`

Ý nghĩa:

- `02:50 UTC`
- `09:50` giờ Việt Nam

Nếu muốn đổi giờ tự động:

1. sửa cron trong file workflow
2. commit
3. push lên `main`

## 6. Chỗ sửa logic report

### Preset mặc định

File:

- `presets/ffvn_daily.json`

Dùng file này để đổi:

- category cần track
- platform cần track
- hashtag filter
- event hashtag
- top limit
- minimum views của trend video
- title mặc định khi gửi SeaTalk

### Text và cách hiển thị report

Các file chính:

- `datasocial/formatter.py`
- `datasocial/report_engine.py`

Dùng để sửa:

- tên các section
- wording khi gửi SeaTalk
- cách hiển thị gọn hay dài
- thứ tự các block trong report

## 7. Chỗ sửa secrets

Trên GitHub:

- `Settings -> Environments -> ffvn-reporting`

Secrets bắt buộc:

- `DATASOCIAL_USESSION`
- `SEATALK_APP_ID`
- `SEATALK_APP_SECRET`
- `SEATALK_GROUP_ID`

## 8. Cách refresh `DATASOCIAL_USESSION`

`DATASOCIAL_USESSION` là cookie session lấy từ website Social Data.

Cách lấy:

1. mở `socialdata.garena.vn`
2. đăng nhập bằng tài khoản đang có quyền
3. mở DevTools của trình duyệt
4. vào phần Cookies hoặc chọn một request GraphQL
5. copy giá trị `usession`
6. cập nhật lại GitHub Environment secret `DATASOCIAL_USESSION`

Nếu cookie này hết hạn thì workflow fetch sẽ fail.

## 9. Cách đọc artifacts

Sau khi workflow chạy xong:

1. mở workflow run
2. kéo xuống phần `Artifacts`
3. tải file zip về
4. giải nén trên máy

Các file phổ biến:

- fetch workflow:
  - `ffvn_daily_latest.csv`
- send/analyze workflow:
  - `ffvn_daily_latest.json`

## 10. Cách xử lý lỗi thường gặp

### Trường hợp A: fetch chạy lâu

Nguyên nhân thường là Social Data phản hồi chậm.

Chỗ cần xem:

- step `Run FFVN daily fetch`

Lưu ý:

- workflow có timeout
- nó không chạy mãi mãi

### Trường hợp B: fetch bị timeout

Ví dụ lỗi:

- `Read timed out`

Cách xử lý:

- tăng timeout
- test với `fetch_window = 1D`
- refresh lại `DATASOCIAL_USESSION`

### Trường hợp C: send workflow fail trước khi gửi SeaTalk

Khả năng:

- không tìm thấy fetch artifact

Cách xử lý:

- kiểm tra fetch workflow trước đó có chạy thành công không
- nếu cần thì chạy tay fetch trước
- rồi chạy lại send

### Trường hợp D: SeaTalk gửi lỗi

Khả năng:

- sai `SEATALK_APP_ID`
- sai `SEATALK_APP_SECRET`
- sai `SEATALK_GROUP_ID`
- bot đã bị remove khỏi group

Cách test nhanh nhất:

- chạy `SeaTalk Test Ping`

### Trường hợp E: muốn sửa text report

Sửa:

- `datasocial/formatter.py`

Sau đó:

1. commit
2. push
3. chạy `FFVN Report Control Panel` để test lại

## 11. Cái gì nên sửa, cái gì không nên sửa lung tung

Thường có thể sửa an toàn:

- rerun workflow
- test bằng control panel với cửa sổ nhỏ
- update secrets
- chạy SeaTalk ping

Cần cẩn thận khi sửa:

- cron schedule
- preset category/platform
- logic report engine

## 12. Quy trình vận hành gợi ý

### Vận hành bình thường

Không cần làm gì.

GitHub sẽ tự:

- fetch lúc `09:00`
- send lúc `09:50`

### Khi thấy có vấn đề

Làm theo thứ tự:

1. kiểm tra `FFVN Daily Fetch (Scheduled)`
2. kiểm tra `FFVN Daily Send (Scheduled)`
3. chạy `SeaTalk Test Ping`
4. nếu cần thì chạy `FFVN Report Control Panel`

## 13. Giới hạn hiện tại của tool

Tool này hiện vẫn phụ thuộc vào:

- cookie session browser của Social Data

Nó chưa dùng service account cố định hay API token chính thức.

Điều đó có nghĩa là:

- nếu `DATASOCIAL_USESSION` hết hạn
- hoặc tài khoản mất quyền

thì workflow fetch sẽ fail cho đến khi bạn cập nhật secret mới.
