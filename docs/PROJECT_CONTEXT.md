# PROJECT CONTEXT

## 1. Tool này dùng để làm gì

Đây là tool Python dùng để:

1. Lấy dữ liệu bài đăng từ hệ thống Social Data private của công ty.
2. Chuẩn hóa dữ liệu export.
3. Phân tích theo rule business cho FFVN.
4. Tạo report ngắn gọn để đọc trên terminal, GitHub Actions và SeaTalk.
5. Gửi report tự động qua bot SeaTalk.

Tool hiện đang phục vụ use case chính:
- báo cáo daily FFVN creator/KOL performance
- dữ liệu lấy từ 4 category chỉ định
- nền tảng TikTok và YouTube

## 2. Repo GitHub

Repo chính:

- [https://github.com/tranducthao243/ffdatareport](https://github.com/tranducthao243/ffdatareport)

## 3. Kiến trúc code hiện tại

Các file lõi:

- `datasocial/cli.py`
  Điều phối CLI, preset, fetch/analyze/send.
- `datasocial/fetcher.py`
  Gọi GraphQL backend Social Data bằng session cookie.
- `datasocial/exporter.py`
  Xử lý `exportInsight`, parse CSV, bridge sang report.
- `datasocial/normalize.py`
  Chuẩn hóa dữ liệu export trước khi phân tích.
- `datasocial/report_engine.py`
  Chứa logic tính các module report.
- `datasocial/formatter.py`
  Format report cho terminal và SeaTalk.
- `datasocial/seatalk.py`
  Lấy token SeaTalk và gửi message.
- `datasocial/timewindows.py`
  Tính window ngày động theo giờ Việt Nam.
- `datasocial/presets.py`
  Nạp preset JSON.
- `presets/ffvn_daily.json`
  Preset production chính đang dùng.

## 4. Data source đang dùng

Tool **không** dùng `listPost` cho report chính.

Tool đang dùng:

- `exportInsight`

Lý do:

- `listPost` thiếu các cột business quan trọng như `view`, `channel name`.
- `exportInsight` trả dữ liệu gần với export thật từ web, usable hơn cho ranking/report.

## 5. Auth hiện tại

### Social Data

Dùng secret:

- `DATASOCIAL_USESSION`

Đây là cookie `usession` lấy từ browser khi tài khoản đang đăng nhập vào Social Data.

Lưu ý:

- đây là auth tạm thời, không phải API token chính thức
- nếu cookie hết hạn hoặc bị rotate thì fetch sẽ fail
- khi fail phải lấy `usession` mới và cập nhật lại GitHub Environment secret

### SeaTalk

Dùng các secret:

- `SEATALK_APP_ID`
- `SEATALK_APP_SECRET`
- `SEATALK_GROUP_ID`

## 6. Preset production hiện tại

Preset đang chạy thật:

- `ffvn_daily`

Nội dung chính:

- `fetch_window = 7D`
- `report_mode = complete_previous_day`
- timezone: `Asia/Ho_Chi_Minh`
- `chunk_by_category = true`
- `chunk_by_day = true`
- category ids:
  - `14`
  - `22`
  - `23`
  - `24`
- platform ids:
  - `0`
  - `2`

Hashtag coverage hiện tại:

- `#freefire`
- `#nhasangtaofreefire`
- `#free_fire`
- `#garenafreefire`
- `#sangtaofreefire`
- `#craftland`
- `#garena`

Event hashtag:

- `#ob53`
- `#giaitriob53`

## 7. Tại sao phải chia chunk

Backend Social Data private khá chậm. Nếu gọi export quá rộng, job hay bị timeout.

Vì vậy tool hiện fetch theo kiểu:

1. tách từng category
2. mỗi category lại tách từng ngày
3. fetch từng chunk riêng
4. gộp lại
5. dedupe dữ liệu

Đây là phần rất quan trọng để tool chạy ổn hơn trên GitHub.

## 8. Report hiện đang có gì

### Top Content 1D

- Top 5 video TikTok có view cao nhất trong 1 ngày gần nhất
- Top 5 video YouTube có view cao nhất trong 1 ngày gần nhất

Ưu tiên hiển thị TikTok trước, YouTube sau.

### Trend Videos 7D

- Top video có view cao bất thường so với baseline trong cùng kênh
- chỉ tính nếu:
  - kênh có ít nhất 3 video trong 7 ngày
  - video có ít nhất 200.000 views

### Daily Views 7D

- ngày có tổng view cao nhất
- ngày có tổng view thấp nhất
- khung giờ đăng dày nhất của top 100 clip view cao nhất trong 7 ngày

### Daily Posts 7D

- ngày có số clip đăng cao nhất
- ngày có số clip đăng thấp nhất

### Top KOLs 7D

- top 5 kênh TikTok theo tổng view 7 ngày
- top 5 kênh YouTube theo tổng view 7 ngày

### Overview 7D

Phần này **không lọc hashtag**, chỉ tính trên toàn bộ dữ liệu đã fetch trong category/platform đã chọn:

- total views
- total clips
- average view

### Campaign Tracking

Chưa làm xong. Đang để future module.

## 9. Workflow GitHub hiện tại

### 1. `SeaTalk Test Ping`

Dùng để test bot SeaTalk nhanh.

Nó:

- không fetch Social Data
- không build report thật
- chỉ gửi một tin nhắn test

Use case:

- test bot còn gửi được không
- test secret SeaTalk có đúng không

### 2. `FFVN Report Control Panel`

Đây là workflow chạy tay.

Nó dùng để:

- test report
- test gửi SeaTalk
- rerun khi cần
- thử các option khác nhau

Những thay đổi bạn chọn trong form của workflow này **chỉ áp dụng cho đúng lần chạy đó**.

Nó **không tự lưu** cấu hình sang workflow scheduled.

### 3. `FFVN Daily Fetch (Scheduled)`

Đây là workflow tự động fetch dữ liệu production.

Lịch hiện tại:

- **09:00 giờ Việt Nam mỗi ngày**

Nó sẽ:

1. fetch dữ liệu theo preset `ffvn_daily`
2. lưu CSV thành artifact

Artifact chính:

- `ffvn-daily-fetch-latest`

CSV chính:

- `outputs/ffvn_daily_latest.csv`

### 4. `FFVN Daily Send (Scheduled)`

Đây là workflow tự động gửi report production.

Lịch hiện tại:

- **09:50 giờ Việt Nam mỗi ngày**

Nó sẽ:

1. tải artifact fetch mới nhất
2. chạy `analyze-only`
3. gửi report qua SeaTalk
4. lưu JSON artifact

Artifact JSON:

- `ffvn-daily-send-latest`

JSON chính:

- `outputs/ffvn_daily_latest.json`

## 10. Quan hệ giữa fetch và send

Hiện nay fetch và send đã tách thành 2 workflow khác nhau.

Lý do:

- fetch có thể mất nhiều phút
- nếu fetch và send nằm chung một workflow, giờ gửi SeaTalk sẽ bị lệch

Mô hình hiện tại:

- 09:00 fetch trước
- 09:50 send sau

Đây là mô hình production chính thức đang dùng.

## 11. Một lưu ý rất quan trọng về artifact

Workflow `FFVN Daily Send (Scheduled)` **không tự fetch data**.

Nó chỉ đọc artifact đã được `FFVN Daily Fetch (Scheduled)` tạo ra trước đó.

Hiện đã có guard:

- nếu không có artifact fetch mới trong vòng 12 giờ gần nhất
- workflow send sẽ fail rõ ràng
- nó sẽ không dùng nhầm artifact cũ

## 12. Cách vận hành hằng ngày

Thông thường:

- không cần bấm tay gì cả
- GitHub sẽ tự chạy:
  - fetch lúc 09:00
  - send lúc 09:50

Chỉ cần vào GitHub khi:

- muốn test
- muốn rerun
- muốn đổi wording
- muốn đổi cron giờ chạy
- muốn cập nhật secrets
- khi workflow báo lỗi

## 13. Khi nào cần bấm tay

### Chỉ để test hoặc rerun

Ví dụ:

- test bot mới
- test report sau khi đổi wording
- rerun một ngày nào đó bị fail

### Không phải việc hằng ngày

Bạn **không phải** vào GitHub bấm mỗi ngày.

## 14. Nếu muốn test ngay

### Test bot nhanh

Chạy:

- `SeaTalk Test Ping`

### Test report nhẹ

Chạy:

- `FFVN Report Control Panel`

Nên dùng:

- `fetch_window = 1D`
- `send_seatalk = false` hoặc `true` tùy mục tiêu

### Test production flow tách riêng

Chạy đúng thứ tự:

1. `FFVN Daily Fetch (Scheduled)`
2. đợi artifact fetch xuất hiện
3. `FFVN Daily Send (Scheduled)`

## 15. Nếu muốn đổi giờ chạy

Sửa các file:

- `.github/workflows/ffvn-daily-fetch.yml`
- `.github/workflows/ffvn-daily-send.yml`

Hiện đang là:

- fetch: `09:00` VN
- send: `09:50` VN

Sau khi sửa:

1. commit
2. push lên GitHub

## 16. Nếu muốn đổi wording report

Sửa các file:

- `datasocial/formatter.py`
- `datasocial/report_engine.py`
- `presets/ffvn_daily.json`

Trong đó:

- đổi text hiển thị chủ yếu ở `formatter.py`
- đổi logic tính report ở `report_engine.py`
- đổi title mặc định ở preset

## 17. Nếu fetch fail thì thường là lỗi gì

### 1. Cookie `usession` hết hạn

Biểu hiện:

- fetch fail
- unauthorized
- GraphQL error
- dữ liệu rỗng bất thường

Fix:

- lấy `usession` mới từ browser
- cập nhật lại secret `DATASOCIAL_USESSION`

### 2. Backend Social Data chậm / timeout

Biểu hiện:

- read timeout
- workflow chạy lâu rồi fail

Fix:

- tăng timeout
- test lại bằng `1D`
- kiểm tra backend nội bộ

### 3. Không có artifact cho workflow send

Biểu hiện:

- `No recent fetch artifact found in the last 12 hours. Run FFVN Daily Fetch (Scheduled) first.`

Fix:

- chạy fetch trước
- hoặc chờ lịch fetch tự chạy

## 18. Những việc còn lại để hoàn thiện hơn

Các bước có thể làm tiếp sau:

- campaign tracking module
- retry chi tiết theo từng chunk fetch
- cảnh báo fail rõ hơn
- gọn giao diện report hơn nữa cho mobile
- nếu sau này cần, làm thêm UI cấu hình ngoài GitHub Actions

## 19. Ghi nhớ ngắn gọn nhất

Nếu cần nhớ cực ngắn, chỉ cần nhớ:

- `SeaTalk Test Ping` = test bot
- `FFVN Report Control Panel` = chạy tay
- `FFVN Daily Fetch (Scheduled)` = auto lấy data lúc 09:00
- `FFVN Daily Send (Scheduled)` = auto gửi report lúc 09:50

Và:

- không cần bấm tay hằng ngày
- chỉ vào GitHub khi test, đổi cấu hình, hoặc xử lý lỗi
