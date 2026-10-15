# Nghiệm thu collector Mega 6/45

Kiểm tra ngày **14/10/2026**, giờ Việt Nam. Phạm vi bàn giao hiện tại: collector,
database và cấu hình cập nhật tự động theo yêu cầu lấy toàn bộ lịch sử.

## Kết quả thực tế

- Đã kết nối PostgreSQL thật và chạy `supabase/migrations/001_collector.sql`.
- Đã nhập **1.575 kỳ** vào bảng `public.mega645_draws` của Supabase.
- Phạm vi mã kỳ: **#00001–#01575**, không thiếu mã kỳ.
- Phạm vi ngày: **20/07/2016–14/10/2026**.
- Audit nguồn thật: `complete_through_observed_source`.
- Không có bản ghi số không hợp lệ, ngày trong tương lai, thứ tự ngày sai hoặc
  mâu thuẫn giữa dữ liệu đang lưu và nguồn trong các lần nhập thành công.
- Kỳ mới nhất: #01575, **06, 16, 19, 21, 34, 43**.
- 1.542 bản ghi mang nhãn `secondary`; 33 kỳ đầu `cross_checked` từ hai nguồn
  thứ cấp. Chưa gán nhãn `official` cho bất kỳ bản ghi nào.

CSV local: `data/mega645.csv`, 1.575 dòng dữ liệu và một dòng tiêu đề, UTF-8 có
BOM để mở trong Excel. Mỗi dòng giữ URL nguồn, thời điểm lấy và trạng thái xác
minh. Báo cáo audit đầy đủ: `artifacts/audit.json`.

## Bằng chứng chạy thật

`artifacts/backfill.json` ghi lần backfill hoàn tất, không thiếu kỳ, không lỗi.
Trước đó collector nhập được #00034 trở đi nhưng Minh Ngọc bỏ trống mã của 33
kỳ đầu. Lỗi được ghi lại, dữ liệu đã nhập được giữ nguyên, sau đó nguồn Việt Mỹ
cung cấp mã kỳ rõ ràng để lấy bù. Lịch sử `ingestion_runs` và 59 `ingestion_issues`
cũ được giữ lại để kiểm tra; đó là lỗi thiếu mã/kỳ trong các lần chạy trước,
không phải 59 bản ghi sai đang tồn tại trong bảng kết quả.

`artifacts/sync-verification.json` ghi lần chạy lại sau backfill:

- Một trang nguồn được đọc; không quét lại toàn bộ lịch sử.
- 0 dòng mới, 10 dòng trùng được bỏ qua, 0 lỗi.
- Database vẫn có đúng 1.575 kỳ.

`collector/scripts/verify_sources.py` tải trực tiếp nguồn đối chiếu theo ngày.
`artifacts/crosschecks.json` xác nhận bốn mẫu:

| Kỳ | Ngày | Sáu số |
| --- | --- | --- |
| #00001 | 20/07/2016 | 02, 17, 33, 37, 38, 45 |
| #00787 | 22/09/2021 | 05, 10, 19, 22, 36, 45 |
| #01571 | 04/10/2026 | 15, 20, 29, 37, 40, 45 |
| #01575 | 14/10/2026 | 06, 16, 19, 21, 34, 43 |

33 kỳ đầu cũng được so sánh sáu số giữa Minh Ngọc và Việt Mỹ ngay trong backfill.
Đối chiếu mẫu không thay thế xác minh chính thức toàn bộ lịch sử.

## Kiểm tra quyền và chống trùng

`collector/scripts/verify_database.py` kiểm tra database thật:

- Cả bốn bảng collector bật RLS.
- `anon` và `authenticated` đọc được kết quả quay, không được INSERT/UPDATE/DELETE.
- Hai role này không đọc được log/issue/batch cache hoặc gọi RPC nhập dữ liệu.
- `service_role` đọc được các bảng quản trị.
- Các kỳ liên tục, sáu số hợp lệ và ngày tăng theo mã kỳ.
- RPC nhập lại ba bản ghi thật không thêm dòng và không sửa dữ liệu hoặc nguồn.
- Gửi lại cùng request ID trả cùng kết quả và không nhân đôi batch.
- Bản ghi có cùng mã kỳ nhưng sáu số khác được ghi issue đúng một lần khi retry,
  giữ nguyên kết quả và nguồn đã lưu.
- CHECK của PostgreSQL từ chối sáu số không tăng nghiêm ngặt.

Báo cáo đã lưu: `artifacts/database-verification.json`.

Các probe database được chạy trong transaction rồi rollback. Không lưu dữ liệu
quay giả hoặc thông tin kiểm thử vào bộ lịch sử thật.

## Kiểm thử mã nguồn

**60 kiểm thử pytest đạt** trên Python 3.12.14: parser từ HTML thật, các lỗi số/mã
kỳ/cấu trúc, nguồn bổ sung, pending/future, SQLite chống trùng và chống ghi đè,
REST retry/pagination, resume/lấp kỳ thiếu, audit và exit code. Kiểm tra tĩnh cả
ba workflow và các script nhúng đạt; input không hợp lệ không đi vào shell.
CSV đã đọc lại từ ổ đĩa và xác nhận đúng 1.575 dòng, kỳ đầu 1 và kỳ cuối 1575.
Đã build được wheel và source distribution trong `artifacts/dist/`.

## Cập nhật cloud còn chờ cấu hình

Workflows `sync.yml`, `backfill.yml`, `ci.yml` đã chuẩn bị với dependency lock,
concurrency, audit nguồn thật và Job Summary. Chưa có workflow GitHub nào đã chạy:
máy này chưa có `gh`, tài khoản GitHub đã xác thực hoặc repository/remote cho dự
án. Vì vậy chưa có link repository hoặc link run để bàn giao.

Trước khi đặt secret cho runner cloud, thay credentials đã xuất hiện trong chat
bằng credentials mới trong `.env`, theo yêu cầu trong tài liệu người dùng. Sau
đó làm các bước cụ thể tại `docs/automation.md`. Dữ liệu và tool local/Supabase
đã chạy thật; cron không hoạt động cho đến khi code lên default branch và secrets
được cấu hình. Không bật dịch vụ trả phí hoặc thay đổi billing.
