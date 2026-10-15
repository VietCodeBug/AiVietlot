# Mega Lab: nghiệm thu giao diện

Ngày kiểm tra: 15/10/2026, giờ Việt Nam.

## Những chức năng đã chạy bằng dữ liệu thật

- Tổng quan đọc Supabase bằng publishable key, hiển thị kỳ mới nhất thực tế và URL nguồn.
- Lịch sử lọc ngày, mã kỳ, số xuất hiện; phân trang phía database.
- Thống kê chỉ dùng đúng phạm vi 30/100/300/tất cả; có tần suất từng số, khoảng vắng,
  cặp số, tổng, chẵn/lẻ, phân bố theo khoảng và ước lượng Bayesian với nhãn xấp xỉ.
- Xác suất hypergeometric chính xác; Jackpot 1/8.145.060; xác suất m dãy khác nhau
  trúng ít nhất một Jackpot bằng m/8.145.060, không cộng giải phụ khi chồng lặp.
- Sinh dãy uniform/frequency/recency: không hoàn lại, dãy không trùng, seed tái lập.
- Lưu sổ thí nghiệm trên thiết bị, chia sẻ/sao chép và đối chiếu toàn bộ lịch sử.
- Backtest walk-forward chạy ở Python: 100 và 300 kỳ gần nhất, 5 dãy/kỳ, 10 seed;
  cùng phạm vi và ngân sách cho ba thuật toán, bootstrap ghép cặp theo khối kỳ/seed.
  Báo cáo thật đã lưu trong `analysis_runs`, không tính lại khi mở dashboard.
- Sáng/tối, cập nhật service worker có thông báo, cài PWA, tải lại route và xem dữ
  liệu công khai đã lưu khi offline. Service worker chỉ cache asset, không cache API/token.

## Kiểm tra

- 12 kiểm thử TypeScript cho xác suất, tần suất theo phạm vi, seed và dãy không trùng.
- 64 kiểm thử Python đạt, gồm kiểm tra các trọng số tại kỳ t chỉ dùng dữ liệu trước t.
- Lint, typecheck và production build đã chạy thành công.
- Playwright với Edge headless: 39 kiểm tra đạt trên dữ liệu thật, không mock nguồn.
  Sáu route ở desktop 1440px và điện thoại 390px/360px không tràn toàn trang;
  điều hướng chạm, phân trang, lọc số, chọn phạm vi, tạo/lưu dãy, CSV, dark mode,
  đọc báo cáo thật và reload offline đều đạt. Không có uncaught browser error.
- Báo cáo máy đọc: `artifacts/web-qa/report.json`; ảnh desktop/mobile ở
  `artifacts/web-qa/`. Mẫu kết quả mới nhất khi kiểm tra là kỳ #01575 ngày 14/10/2026.

## Cấu hình và giới hạn

Lịch sử xổ số dùng quyền đọc public; vé theo dõi chỉ tài khoản sở hữu được đọc,
ghi qua RPC có xác thực và kiểm tra giờ chốt. Chỉ publishable key được đưa vào bundle;
secret key và mật khẩu PostgreSQL không có trong git/public. Trang Theo dõi đã có
đăng ký trước kỳ, khóa dãy/cấu hình, dấu đã mua và trigger tự đối chiếu. Chưa gửi
email thông báo kết quả. Các kết quả nghiên cứu chưa chứng minh lợi thế dự báo.

Đã deploy và nối GitHub qua Vercel CLI trong CMD. Production đã READY:
**https://mega-lab-iota.vercel.app**. Chính URL này được kiểm tra trình duyệt
trên dữ liệu thật, gồm reload offline và sáu route desktop/mobile. Project nằm trên
gói Hobby hiện có; không thay đổi billing.

Sổ thí nghiệm mới giữ nguyên cấu hình, seed, phiên bản thuật toán, mã kỳ đầu/cuối,
số mẫu và SHA-256 dữ liệu đầu vào tại lúc tạo. Làm mới dữ liệu sau đó không đổi
nguồn huấn luyện đã gắn với bộ dãy cũ. Không tự xóa các thí nghiệm cũ khi lưu bộ mới.

Luồng Theo dõi đạt 16 kiểm tra trình duyệt riêng, gồm căn giữa bóng số, đăng nhập
thật bằng tài khoản thử không gửi email, lưu 5 vé, đánh dấu mua, tải lại, lọc vé mua,
đăng xuất xóa nội dung riêng và viewport 360/390/768/1440px. Tài khoản và vé thử được
xóa sau kiểm tra. Các kiểm tra database trong transaction rollback xác nhận RLS,
chống backdate, hash, khóa giờ chốt, kết quả đúng kỳ gồm cả trượt, idempotency và revisions.
Chi tiết tại [prospective-research.md](prospective-research.md).

Cloud sync đã đạt [lần chạy thực tế](https://github.com/VietCodeBug/AiVietlot/actions/runs/38663883094),
gồm nhập kết quả, xuất phân tích và audit sau khi cấu hình Secrets theo xác nhận người dùng.
