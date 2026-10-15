# Vietlott Mega 6/45 Collector

Tool Python 3.12 thu thập lịch sử Mega 6/45, lưu vào Supabase hoặc SQLite, lấy bù kỳ thiếu, kiểm tra dữ liệu và xuất CSV cho đồ án thống kê, xác suất. Phạm vi hiện tại là collector, database và cập nhật tự động. Dashboard, PWA, mô hình dự đoán và email chưa thuộc bản này.

**Đã nhập dữ liệu thật vào Supabase:** audit ngày 14/10/2026 xác nhận 1.575 kỳ từ #00001 ngày 20/07/2016 đến #01575 ngày 14/10/2026, không thiếu mã kỳ, không có bản ghi sai hoặc mâu thuẫn. Đây là ảnh chụp nghiệm thu tại thời điểm kiểm tra; CLI luôn đọc phạm vi hiện tại từ DB và nguồn, không hardcode kỳ cuối.

Bằng chứng, mức xác minh nguồn và trạng thái triển khai nằm trong [docs/acceptance.md](docs/acceptance.md). Repository GitHub và workflow cloud chưa có URL đã xác minh; xem các điều kiện còn thiếu ở phần triển khai.

## Nguồn và mức xác minh

- Nguồn chính thức được khảo sát: [Vietlott Mega 6/45](https://vietlott.vn/vi/trung-thuong/ket-qua-trung-thuong/645.html); môi trường kiểm tra trả HTTP 403, nên dữ liệu chưa được gán nhãn `official`.
- Adapter đang hoạt động: [Minh Ngọc Mega 6/45](https://www.minhngoc.net.vn/ket-qua-xo-so/dien-toan-vietlott/mega-6x45.html). Parser đọc HTML thật và các liên kết lịch sử quan sát được; không tạo URL kỳ quay từ lịch dự kiến.
- Bản ghi nhập từ Minh Ngọc mang `source_name=minhngoc`, `verification_status=secondary`, URL nguồn và `fetched_at`. Đây là dữ liệu nguồn phụ, chưa mặc nhiên được Vietlott xác minh chính thức.
- Minh Ngọc để trống mã kỳ ở 33 kỳ đầu. Adapter bổ sung mã kỳ rõ ràng từ trang [Việt Mỹ theo ngày](https://xosovietmy.vn/xs-mega-ngay-20-07-2016.html), chỉ chấp nhận khi cùng ngày và sáu số khớp Minh Ngọc. Bản ghi mang `source_name=xosovietmy+minhngoc`, `verification_status=cross_checked`; nghĩa là hai nguồn phụ khớp nhau, chưa phải xác minh chính thức.

Chi tiết HTML, liên kết lịch sử và giới hạn đối chiếu: [docs/sources.md](docs/sources.md). Snapshot nghiệm thu có 1.542 kỳ `secondary` và 33 kỳ `cross_checked`.

Collector chỉ nhận kỳ có mã và ngày hợp lệ, đủ sáu số khác nhau trong 1–45, sắp tăng dần. Kết quả chưa quay hoặc đang cập nhật dở được bỏ qua để thử lại. Timeout kết nối/đọc là 10/40 giây, retry tối đa ba lần với exponential backoff, khoảng nghỉ mặc định một giây/request và tối thiểu 0,5 giây.

Thống kê lịch sử không bảo đảm dự đoán số trúng. Dữ liệu thu thập chỉ phục vụ nghiên cứu xác suất và kiểm thử.

## Cài đặt local

Cần Python 3.12. Các lệnh bên dưới chạy từ thư mục repository trong PowerShell, không cần kích hoạt virtualenv.

Với Python 3.12 đã cài trên máy:

```powershell
py -3.12 -m venv .venv
.venv\Scripts\python.exe -m pip install --require-hashes -r requirements-dev.txt
.venv\Scripts\python.exe -m pip install --no-deps .
```

`requirements-dev.txt` gồm runtime và pytest; nếu chỉ chạy collector, dùng `requirements.txt`. Cả hai lock file khóa phiên bản dependency trực tiếp, gián tiếp và SHA256. Linux/macOS dùng `python3.12 -m venv .venv` và `.venv/bin/python`, `.venv/bin/mega-collector`.

Nếu dùng `uv`, đây là lựa chọn thay thế; virtualenv do `uv` tạo có thể không chứa pip:

```powershell
uv venv --python 3.12 .venv
uv pip install --python .venv\Scripts\python.exe --require-hashes -r requirements-dev.txt
uv pip install --python .venv\Scripts\python.exe --no-deps .
```

Sau khi thay đổi dependency, tạo lại lock theo [docs/automation.md](docs/automation.md), kiểm thử rồi mới đẩy mã.

## Cấu hình Supabase và tạo bảng

Sao chép file mẫu và điền cấu hình mới bằng editor:

```powershell
Copy-Item .env.example .env
```

Collector cần `SUPABASE_URL` và `SUPABASE_SECRET_KEY`; đọc từ môi trường hoặc `.env`. Không dùng publishable key để nhập dữ liệu. Secret key, mật khẩu PostgreSQL và `.env` chỉ nằm ở máy local hoặc secret store phía runner. `.gitignore` loại `.env`, virtualenv, dữ liệu và artifacts khỏi repository public.

**Đổi credentials từng xuất hiện trong chat trước khi cấu hình GitHub/public cloud.** Chỉ đưa credentials mới vào `.env` local và GitHub Actions Secrets. Không đặt secret trong README, command line, frontend hoặc log.

Migration hoàn chỉnh: [supabase/migrations/001_collector.sql](supabase/migrations/001_collector.sql). Có hai cách chạy:

1. Mở Supabase **SQL Editor**, dán toàn bộ migration và chạy.
2. Điền kết nối PostgreSQL trong `.env`, rồi dùng script:

```powershell
.venv\Scripts\python.exe collector\scripts\migrate.py
```

Với mật khẩu chứa `@`, `#`, `[` hoặc `]`, ưu tiên các trường tách riêng để tránh lỗi URI:

```dotenv
PGHOST=replace-with-exact-host-from-supabase-connect
PGPORT=5432
PGDATABASE=postgres
PGUSER=replace-with-exact-user-from-supabase-connect
PGPASSWORD='replace-with-new-password'
```

Các ký tự trong mật khẩu là một phần của mật khẩu; không tự thêm ngoặc vuông bao quanh. Nếu dùng `DATABASE_URL`, phải URL-encode các ký tự đặc biệt trong password. Script ưu tiên `PGHOST` và các trường `PG*` nếu đã đặt, yêu cầu SSL và không in URI/mật khẩu khi lỗi.

Nếu direct PostgreSQL không truy cập được vì mạng IPv6, mở Supabase **Connect → Session pooler**, sao chép chính xác host, port, database và user ở đó. Không đoán địa chỉ pooler. REST secret key không tự cấp quyền thực thi SQL/DDL.

Database có `mega645_draws`, `ingestion_runs`, `ingestion_issues` và `ingestion_batches`. Mã kỳ là khóa chính, ngày quay unique; CHECK bắt buộc `1 <= n1 < n2 < n3 < n4 < n5 < n6 <= 45`. RLS cho phép đọc công khai kết quả quay theo yêu cầu dữ liệu public, giữ metadata nhập riêng và chỉ `service_role` được ghi. Không có quyền ghi công khai.

## Các lệnh

Đặt tùy chọn global như `--backend`, `--database`, `--env-file` **trước** tên lệnh:

```powershell
.venv\Scripts\mega-collector.exe --help
.venv\Scripts\mega-collector.exe backfill --help
.venv\Scripts\mega-collector.exe sync --help
.venv\Scripts\mega-collector.exe audit --help
.venv\Scripts\mega-collector.exe export --help
.venv\Scripts\mega-collector.exe import-local --help
```

Nhập toàn bộ lịch sử có thể quan sát vào Supabase; chạy lại để tiếp tục nếu gián đoạn:

```powershell
.venv\Scripts\mega-collector.exe --backend supabase backfill --checkpoint artifacts/backfill.json
.venv\Scripts\mega-collector.exe --backend supabase sync
.venv\Scripts\mega-collector.exe --backend supabase audit --check-source --output artifacts/audit.json
.venv\Scripts\mega-collector.exe --backend supabase export --output data/mega645.csv
```

`backfill --max-pages 5` giới hạn số trang của một lần chạy; bỏ tùy chọn này để nhập đến hết phạm vi nguồn. Checkpoint là bằng chứng tiến độ, còn resume dựa trên dữ liệu đã ghi và mã kỳ thiếu trong DB. Máy GitHub mới không cần có checkpoint của máy cũ.

Sync mặc định tối đa 30 trang và lấy bù các khoảng trống; dùng `--max-pages` lớn hơn nếu cần. Khi DB đã liên tục đến kỳ mới nhất quan sát được, sync thường chỉ đọc trang nguồn mới nhất, không quét lại toàn bộ lịch sử. Lần nghiệm thu sau backfill thực tế đọc một trang, thêm 0 kỳ, bỏ qua an toàn 10 kỳ trùng và không có lỗi. Nếu còn khoảng thiếu vượt giới hạn lần chạy, chạy tiếp hoặc dùng backfill.

Có thể thu thập vào SQLite trước, không cần credentials Supabase:

```powershell
.venv\Scripts\mega-collector.exe --backend sqlite --database data/mega645.sqlite3 backfill
.venv\Scripts\mega-collector.exe --backend sqlite --database data/mega645.sqlite3 audit --check-source --output artifacts/local-audit.json
.venv\Scripts\mega-collector.exe --backend sqlite --database data/mega645.sqlite3 export --output data/mega645.csv
```

Đưa dữ liệu SQLite đã thu thập lên Supabase sau khi chạy migration và cấu hình `.env`:

```powershell
.venv\Scripts\mega-collector.exe --backend supabase import-local --input data/mega645.sqlite3 --batch-size 200
.venv\Scripts\mega-collector.exe --backend supabase audit --check-source --output artifacts/audit.json
```

Batch tối đa 1.000 kỳ. Nhập lại cùng mã, ngày và sáu số được bỏ qua an toàn. Nếu nội dung hoặc ngày mâu thuẫn, hệ thống lưu issue và báo lỗi, giữ nguyên kết quả đang có. Không tự tạo số hoặc suy ra kết quả cho kỳ thiếu.

CSV dùng UTF-8 có BOM để mở thuận tiện trong Excel; chứa mã kỳ, ngày, sáu số, nguồn, URL, thời điểm lấy và mức xác minh.

## Đọc audit và mã thoát

Audit báo tổng kỳ, kỳ/ngày đầu và cuối, danh sách `missing_draw_ids`, dữ liệu sai, thứ tự ngày không hợp lệ, issues và mâu thuẫn. `--check-source` đọc nguồn thật để so sánh thêm kỳ mới nhất; lỗi nguồn là lỗi, không phải "chưa có kỳ mới".

| `coverage` | Ý nghĩa |
| --- | --- |
| `complete_through_observed_source` | Mã kỳ liên tục từ 1 đến phạm vi mới nhất đã quan sát, không có lỗi dữ liệu/mâu thuẫn; mức xác minh nguồn vẫn giữ riêng |
| `contiguous_local_range` | Mã kỳ local liên tục; chưa kiểm tra kỳ mới nhất của nguồn trong lần audit này |
| `incomplete_or_has_issues` | Còn kỳ thiếu, dữ liệu sai hoặc mâu thuẫn cần kiểm tra |

"Đầy đủ" chỉ áp dụng cho phạm vi nguồn đã quan sát tại thời điểm audit, không bảo đảm nguồn phụ luôn đầy đủ hoặc được xác minh chính thức.

| Exit code | Ý nghĩa |
| --- | --- |
| `0` | Lệnh hoàn tất trong phạm vi được báo cáo |
| `1` | Cấu hình hoặc truy cập file lỗi |
| `2` | Phạm vi chưa đầy đủ/audit có lỗi, hoặc tham số CLI sai |
| `3` | Không truy cập/đọc được nguồn hợp lệ |
| `4` | Không đọc/ghi được database |
| `5` | Thu thập/import phát hiện lỗi dữ liệu hoặc mâu thuẫn |

## GitHub Actions

Ba workflow đã chuẩn bị: [sync.yml](.github/workflows/sync.yml), [backfill.yml](.github/workflows/backfill.yml), [ci.yml](.github/workflows/ci.yml).

Trong repository public, thêm `SUPABASE_URL` và `SUPABASE_SECRET_KEY` mới tại **Settings → Secrets and variables → Actions**. Đẩy mã, migration và workflows lên default branch, chạy **Mega 6-45 backfill → Run workflow**, rồi chạy **Mega 6-45 sync** và kiểm tra Job Summary/artifacts thật.

| Cron UTC | Giờ Việt Nam |
| --- | --- |
| `45 11 * * 0,3,5` | 18:45, Chủ nhật/thứ Tư/thứ Sáu |
| `15 12 * * 0,3,5` | 19:15, Chủ nhật/thứ Tư/thứ Sáu |
| `15 13 * * 0,3,5` | 20:15, Chủ nhật/thứ Tư/thứ Sáu |
| `17 2 * * *` | 09:17 mỗi ngày để lấy bù |

Backfill chỉ chạy thủ công. Hai workflow nhập dùng concurrency chung, không hủy job đang nhập; audit sau nhập có `--check-source`. Permissions GitHub chỉ `contents: read`, actions khóa theo SHA, dependencies theo lock hashes. Job Summary ghi số dòng mới/trùng/lỗi và kỳ mới nhất DB; audit/checkpoint lưu artifact 30 ngày.

GitHub cron có thể chạy chậm hoặc bỏ lỡ; sync lấy bù theo dữ liệu DB. Sau khi triển khai cloud, collector chạy khi máy cá nhân tắt. Không kích hoạt dịch vụ trả phí hoặc thay đổi billing.

**Điều kiện cloud còn thiếu:** máy hiện chưa có `gh` trong PATH/thư mục cài phổ biến, chưa xác minh GitHub authentication và chưa có repository/remote. Cần credentials đã đổi trước cloud. Vì vậy chưa có link repository hoặc workflow đã chạy để bàn giao. Hướng dẫn cài `gh`, đăng nhập, cấu hình secrets và nghiệm thu tại [docs/automation.md](docs/automation.md).

## Kiểm thử và xử lý lỗi

```powershell
.venv\Scripts\python.exe -m pytest -q
.venv\Scripts\python.exe -m compileall -q collector
```

Tests gồm parser với fixture HTML thật, thiếu số, số trùng, ngoài khoảng, cấu trúc thay đổi, nhập lại và phát hiện mâu thuẫn. Kết quả chạy nguồn thật, migration, DB thật đọc lại và giới hạn truy cập được ghi riêng trong [docs/acceptance.md](docs/acceptance.md); tests không thay thế nghiệm thu dữ liệu thật.

- **Nguồn lỗi/thay đổi HTML:** xem `source_error` và issues, lưu HTML mới, sửa parser/fixture, chạy tests rồi thử lại. Không coi trang không có kết quả là lịch sử rỗng.
- **Database lỗi:** kiểm tra migration, secret phía server, host/pooler và quyền truy cập; không dùng publishable key thay cho secret.
- **Mâu thuẫn:** xem `ingestion_issues`, đối chiếu nguồn có bằng chứng trước khi xử lý; collector không ghi đè âm thầm.
- **Backfill gián đoạn:** chạy lại cùng backend, audit có `--check-source`; xem mã kỳ còn thiếu thay vì đoán từ lịch quay.
- **Workflow thất bại:** xem bước lỗi, Job Summary và artifact audit; phân biệt chưa có kỳ mới, lỗi nguồn và lỗi DB. Chạy lại khi đã sửa nguyên nhân.

## Cấu trúc

```text
collector/mega_collector/  Parser, validation, storage, engine và CLI
collector/scripts/        Script migration PostgreSQL
collector/tests/          Tests và fixture HTML thật
supabase/migrations/      SQL schema, RLS và RPC nhập batch
.github/workflows/        Sync, backfill và CI
docs/automation.md        Hướng dẫn triển khai cloud
docs/acceptance.md        Bằng chứng nghiệm thu thực tế
docs/sources.md           Nguồn và giới hạn xác minh
requirements*.txt         Dependency locks có hashes
.env.example              Cấu hình mẫu, không chứa credentials thật
```
