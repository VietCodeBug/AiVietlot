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
- Playwright với Edge headless: 38 kiểm tra đạt trên dữ liệu thật, không mock nguồn.
  Sáu route ở desktop 1440px và điện thoại 390px/360px không tràn toàn trang;
  điều hướng chạm, phân trang, lọc số, chọn phạm vi, tạo/lưu dãy, CSV, dark mode,
  đọc báo cáo thật và reload offline đều đạt. Không có uncaught browser error.
- Báo cáo máy đọc: `artifacts/web-qa/report.json`; ảnh desktop/mobile ở
  `artifacts/web-qa/`. Mẫu kết quả mới nhất khi kiểm tra là kỳ #01575 ngày 14/10/2026.

## Cấu hình và giới hạn

Giao diện public dùng quyền chỉ đọc của Supabase. Chỉ publishable key được đưa vào
bundle; secret key và mật khẩu PostgreSQL ở `.env` backend, không có trong git/public.
Thí nghiệm lưu trong trình duyệt chưa đăng ký lên server, chưa có khóa dự đoán theo
kỳ, chưa gửi email. Các kết quả thống kê/backtest chưa chứng minh lợi thế dự báo.

Vercel đang được liên kết bằng CLI theo yêu cầu. Chỉ ghi URL production và trạng
thái thành công vào tài liệu sau khi deployment thật hoàn tất.
