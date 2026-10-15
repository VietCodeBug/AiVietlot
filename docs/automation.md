# Triển khai tự động collector

Workflows đã chuẩn bị để collector chạy trên GitHub Actions; máy cá nhân có thể tắt sau khi cấu hình cloud. Database Supabase thật đã được tạo và backfill/audit đã chạy từ môi trường local. Phần này chỉ thu thập Mega 6/45, chưa triển khai dashboard, dự đoán hay email.

## Điều kiện trước khi triển khai

1. Đổi mật khẩu PostgreSQL và secret key đã xuất hiện trong chat. Ghi credentials mới vào `.env` local, không commit file này.
2. Chạy migration trong thư mục `supabase/migrations/` bằng kết nối PostgreSQL hoặc Supabase SQL Editor. Secret REST key không thực thi được DDL.
3. Cài GitHub CLI (`gh`) và đăng nhập bằng `gh auth login`; kiểm tra bằng `gh auth status`.
4. Dùng repository public theo yêu cầu của dự án. Public repository giữ secret key trong GitHub Actions Secrets; public chỉ có nghĩa là mã nguồn công khai.

Nếu direct PostgreSQL không hoạt động do IPv6, mở Supabase **Connect**, lấy chính xác chuỗi **Session pooler** của dự án. Không đoán hostname, port hay username pooler.

## Cấu hình GitHub

Trong repository, mở **Settings → Secrets and variables → Actions → New repository secret**, thêm `SUPABASE_URL` và `SUPABASE_SECRET_KEY` từ `.env` đã thay mới. Không cần PostgreSQL password, publishable key hoặc JWKS URL trong workflow nhập dữ liệu.

Nếu dùng CLI, `gh secret set SUPABASE_URL` và `gh secret set SUPABASE_SECRET_KEY` nhận giá trị bằng lời nhắc tương tác; tránh đưa giá trị vào command line hoặc lịch sử shell.

Đẩy toàn bộ mã, migration và `.github/workflows/` lên default branch. Lịch cron chỉ chạy workflow từ default branch. GitHub token của workflow chỉ có quyền `contents: read`; collector dùng Supabase secret phía runner để ghi dữ liệu.

## Backfill và resume

Mở **Actions → Mega 6-45 backfill → Run workflow**. Để `max_pages` trống để nhập toàn bộ lịch sử mà nguồn cung cấp; đặt số nguyên dương khi muốn một lần nhập giới hạn.

Mỗi runner mới có filesystem mới. Resume dựa vào dữ liệu đã ghi trong database và mã kỳ còn thiếu, không dựa vào một checkpoint được kỳ vọng còn trên máy GitHub. Artifact `backfill.json` hỗ trợ kiểm tra lần chạy; `audit.json` là báo cáo trạng thái database sau lần nhập. Khi gián đoạn, chạy lại workflow; nội dung trùng được bỏ qua và mâu thuẫn được ghi vào bảng issues.

Audit luôn chạy sau bước nhập, kể cả khi bước nhập lỗi, với `--check-source` để so sánh kỳ mới nhất quan sát được với DB. Một lần backfill có giới hạn có thể chưa lấp hết lịch sử và audit phải phản ánh điều đó. Không coi workflow xanh hoặc có checkpoint là bằng chứng đủ toàn bộ kỳ.

## Lịch cập nhật

| Cron UTC | Giờ Việt Nam | Mục đích |
| --- | --- | --- |
| `45 11 * * 0,3,5` | 18:45, Chủ nhật/thứ Tư/thứ Sáu | Lấy kết quả sau kỳ dự kiến |
| `15 12 * * 0,3,5` | 19:15, Chủ nhật/thứ Tư/thứ Sáu | Thử lại nguồn chậm |
| `15 13 * * 0,3,5` | 20:15, Chủ nhật/thứ Tư/thứ Sáu | Thử lại nguồn chậm |
| `17 2 * * *` | 09:17 mỗi ngày | Lấy bù kỳ bị bỏ lỡ |

Lịch chỉ kích hoạt kiểm tra nguồn. Không coi lịch dự kiến là bằng chứng đã quay. GitHub có thể trì hoãn hoặc bỏ lỡ lần cron; sync kiểm tra kỳ mới và kỳ thiếu để phục hồi. Workflow cũng có **Run workflow** để chạy thủ công.

Hai workflow nhập dùng cùng concurrency group `mega645-ingestion`, `cancel-in-progress: false`; GitHub không hủy lần nhập đang chạy. GitHub chỉ giữ một lần chạy pending trong cùng group, nên việc lấy bù không phụ thuộc số lần trigger đã được giữ trong hàng đợi.

Timeout: sync 60 phút, backfill 180 phút, CI 15 phút. Các action được khóa theo SHA. `requirements.txt` và `requirements-dev.txt` khóa toàn bộ phiên bản dependency trực tiếp, gián tiếp và SHA256 của gói; workflow cài bằng `--require-hashes`, sau đó cài project bằng `--no-deps`. Build backend được khóa trong `pyproject.toml`.

Khi chủ động thay dependency, tạo lại lock bằng Python 3.12 và kiểm thử trước khi đẩy:

```powershell
uv pip compile pyproject.toml --python .venv/Scripts/python.exe --universal --generate-hashes --output-file requirements.txt
uv pip compile pyproject.toml --extra test --python .venv/Scripts/python.exe --universal --generate-hashes --output-file requirements-dev.txt
```

## Nghiệm thu cloud

Sau khi có repository và secrets mới:

```powershell
gh workflow run backfill.yml
gh run list --workflow backfill.yml
gh run view <RUN_ID> --log-failed
gh workflow run sync.yml
gh run list --workflow sync.yml
```

Kiểm tra Job Summary có số dòng mới, số dòng trùng, lỗi và kỳ mới nhất trong DB. Tải artifact audit, xác nhận phạm vi kỳ từ đầu đến cuối, danh sách kỳ thiếu, dữ liệu không hợp lệ và issues. Đọc lại vài kỳ trong Supabase để xác nhận việc ghi thật. Lưu URL của hai lần chạy vào hồ sơ nghiệm thu; không ghi link giả nếu chưa chạy trên GitHub.

Nếu nguồn thay đổi, sửa parser dựa trên HTML thật mới, cập nhật fixture, chạy CI rồi mới chạy lại. Nếu gặp lỗi DB, kiểm tra migration, secrets và trạng thái Supabase. Nếu có mâu thuẫn, giữ nguyên bản ghi hiện có, đối chiếu nguồn và xử lý issues có bằng chứng; không ghi đè bằng script tùy tiện.

Tài liệu chính thức: [scheduled workflows](https://docs.github.com/en/actions/writing-workflows/choosing-when-your-workflow-runs/events-that-trigger-workflows#schedule), [concurrency](https://docs.github.com/en/actions/using-jobs/using-concurrency), [Actions secrets](https://docs.github.com/en/actions/security-for-github-actions/security-guides/using-secrets-in-github-actions).

## Trạng thái máy khi chuẩn bị mã

Nghiệm thu local ngày 14/10/2026: Supabase thật có 1.575 kỳ, phạm vi #00001 ngày 20/07/2016 đến #01575 ngày 14/10/2026; audit có kiểm tra nguồn không thiếu mã kỳ, không có bản ghi sai hoặc mâu thuẫn. Sync tiếp theo đọc một trang, thêm 0 kỳ, bỏ qua 10 kỳ trùng và không có lỗi. Xem [acceptance.md](acceptance.md) cho bằng chứng đầy đủ; các số ở đây là snapshot, không phải cấu hình collector.

Đã kiểm tra Git có sẵn; GitHub CLI chưa có trong `PATH` và các thư mục cài phổ biến. Workspace chưa có `.git` hay remote repository, nên chưa xác minh được GitHub account hoặc chạy workflow cloud. Credentials phải được đổi trước cloud theo yêu cầu trong tài liệu người dùng. Những điểm này là điều kiện triển khai còn thiếu; dữ liệu Supabase đã nhập thật không đồng nghĩa lịch GitHub đã hoạt động.
