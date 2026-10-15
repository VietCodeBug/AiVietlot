# Theo dõi vé trước kỳ quay

Trang `/theo-doi` dùng Supabase Auth email/password. Đăng ký cần xác nhận email theo cấu hình Auth hiện tại; sau xác nhận quay lại app để đăng nhập. Dữ liệu từng tài khoản được bảo vệ bằng RLS. Lịch sử kết quả xổ số vẫn đọc công khai.

Tạo dãy tại Thí nghiệm → **Đưa vào theo dõi** → chọn các dãy tự khai báo đã mua → **Lưu cho kỳ**. Chỉ thông báo đã lưu sau khi RPC thành công; draft trong sessionStorage chưa phải đăng ký. Dãy, seed, phiên bản thuật toán, cấu hình, phạm vi và SHA-256 dữ liệu đầu vào được cố định. Server kiểm tra hash với lịch sử thật và ghi thời điểm tạo. Gửi lại cùng dãy cùng kỳ trả bản ghi cũ; không thay thuật toán hoặc dấu mua của bản ghi cũ.

Kỳ mục tiêu luôn là mã kết quả mới nhất + 1. Ngày dự kiến theo lịch thứ Tư/Sáu/Chủ nhật, chốt sớm lúc **17:45 giờ Việt Nam**. Đây là quy tắc nghiên cứu của app, không phải xác nhận lịch của Vietlott. Khi quá giờ chốt mà collector chưa nhập kết quả, không tự nhảy qua kỳ khác. Có thể sửa dấu mua trước giờ chốt; sau đó server khóa ngay cả khi đồng hồ trình duyệt sai. Không có thao tác xóa vé để loại các lần trượt khỏi thống kê.

Migration `003_prospective_research.sql` thêm trigger trên kết quả thật. Khi collector nhập kỳ mới, trigger đối chiếu từng vé có đúng mã kỳ, lưu 0–6 số khớp và nguồn; gọi lại không tạo kết quả trùng. Nếu kết quả được hiệu chỉnh có kiểm soát, lưu bản trước trong bảng revisions. Bản ghi sai điều kiện thời gian không tính vào kết quả nghiên cứu. Dấu mua là tự khai báo, không phải xác minh giao dịch mua vé.

Mỗi vé có một dãy đối chứng ngẫu nhiên được server cố định cùng lúc, không trùng đối chứng khác trong cùng tài khoản/kỳ. Thống kê so sánh tỷ lệ khớp từ 3 số giữa hai nhóm vé ghép cặp cùng kỳ; hiển thị toàn bộ hoặc chỉ vé đã mua. Khoảng bootstrap 95% lấy mẫu theo cụm kỳ, 1.000 lượt, cần ít nhất hai kỳ. Mẫu nhỏ, lựa chọn vé để mua và nhiều phương pháp được thử có thể gây thiên lệch; tỷ lệ quan sát cao hơn chưa chứng minh khả năng dự đoán. Xác suất Jackpot lý thuyết vẫn là 1/8.145.060 mỗi tổ hợp.

Kiểm chứng database: `python collector/scripts/verify_research.py` chạy fixture trong transaction rồi rollback toàn bộ; kiểm tra quyền sở hữu, khóa thời gian, hash, chống backdate, hit/miss, idempotency và lịch sử hiệu chỉnh. `python scripts/verify_research_browser.py` tạo tài khoản Auth tạm đã xác nhận bằng Admin API (không gửi email), kiểm tra đăng nhập/lưu vé/đánh dấu mua qua UI rồi xóa tài khoản và các vé thử trong `finally`. Không tạo kỳ xổ số giả để giữ trong database thật. Báo cáo tại `artifacts/research-database-verification.json` và `artifacts/web-qa/research-report.json`.

Realtime và polling 60 giây cập nhật sổ khi đang mở. Tự đối chiếu chạy ở database, không cần giữ tab mở. Collector chạy cloud phụ thuộc GitHub Actions Secrets và workflow sync; triển khai giao diện không tự bật secrets. Chưa có gửi thông báo email kết quả.

## Vé mua trước khi dùng sổ

Migration `004_purchase_reports.sql` thêm sổ **Vé đã mua · khai báo bổ sung**. Ngày mua tự khai báo và `recorded_at` do server ghi là hai trường riêng; các vé này không được đưa vào nhóm dự đoán tiến cứu hoặc baseline để tránh ghi lùi dữ liệu nghiên cứu. Người dùng chọn đúng mã kỳ trên vé; kết quả được nối theo chính mã kỳ và tự cập nhật khi collector có dữ liệu.

Nếu yêu cầu nhập vé từ cuộc trò chuyện chưa xác định tài khoản, quản trị nhập bản ghi chưa có chủ và trao link nhận riêng có UUID ngẫu nhiên. Chỉ tài khoản đã xác nhận email mới được nhận, một lần; tài khoản khác không đọc được bản ghi và không thể nhận lại. Không commit link nhận hoặc email người dùng vào repo. `verify_purchase_reports.py` kiểm tra quyền sở hữu, idempotency, ngày mua, số hợp lệ và cách ly thống kê trong transaction rollback.

Lịch sử có lọc nhanh kỳ mới nhất/ngày có kết quả mới nhất và thứ tự ngày tăng/giảm, áp dụng cả trên database và dữ liệu offline. Hai nút mới nhất bỏ bộ lọc số cũ để không nhầm kết quả mới nhất có một số cụ thể với kết quả mới nhất toàn bộ dữ liệu. Đăng nhập kiểm tra email đầy đủ và giải thích các mã Auth lỗi tại form; người dùng cần tạo tài khoản Mega Lab riêng trước lần đăng nhập đầu.
