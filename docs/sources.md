# Nguồn dữ liệu và giới hạn xác minh

Kiểm tra trực tiếp ngày 14/10/2026, múi giờ Việt Nam.

## Vietlott

Nguồn chính thức được ưu tiên: <https://vietlott.vn/vi/trung-thuong/ket-qua-trung-thuong/645.html>.
Trong môi trường chạy này, truy cập trang kết quả trả HTTP 403. Collector không
vượt chặn và không gán nhãn `official` cho dữ liệu lấy từ các trang thứ cấp.

## Minh Ngọc

Trang bắt đầu thực tế:
<https://www.minhngoc.net.vn/ket-qua-xo-so/dien-toan-vietlott/mega-6x45.html>.

HTML đã tải và lưu trong `minhngoc_probe.html`. Fixture kiểm thử tối giản
`collector/tests/fixtures/minhngoc-index.html` giữ nguyên mười khối kết quả,
đường dẫn theo ngày và liên kết quay về ngày đầu. Cấu trúc quan sát:

- Mỗi khối `.box-result-detail` chứa mã kỳ trong `#DT6X45_KY_VE`, ngày quay và
  sáu phần tử `ul.result-number > li`.
- Liên kết ngày trong `.boxkqxsdientoan h4 a[href]` là URL nguồn của từng bản ghi.
- Mười kỳ trên trang đầu: #01575 ngày 14/10/2026 đến #01566 ngày 23/09/2026.
- Liên kết `<<<<` trỏ tới trang ngày 20/07/2016.
- Trình thu thập đi tới URL của kết quả cũ nhất đang nhìn thấy. Trang ngày có
  kết quả tại ngày mốc và các kỳ trước; một kết quả chồng lặp được xử lý bởi
  kho dữ liệu. Không cần đoán API hoặc dùng offset giả.

Các bản ghi lấy từ nguồn này mang nhãn `secondary`. Cấu trúc thay đổi, mã kỳ
không hợp lệ hoặc sáu số không hợp lệ được lưu thành lỗi thay vì tự tạo kết quả.
Kết quả trong tương lai, trước 18:05 trong ngày hoặc chưa đủ số trong ngày được
để chờ.

Các kỳ đầu #00001–#00033 có sáu số nhưng Minh Ngọc để trống mã kỳ. Collector
không suy ra mã kỳ bằng lịch quay hay đếm ngày.

## Việt Mỹ bổ sung các kỳ thiếu mã

Trang đầu đã tải trực tiếp:
<https://xosovietmy.vn/xs-mega-ngay-20-07-2016.html>.
HTML đầy đủ lưu tại `artifacts/vietmy-first.html`; fixture tối giản tại
`collector/tests/fixtures/vietmy-first.html` giữ nguyên `section.section`, tiêu
đề ngày, mã kỳ và kết quả.

Trang này ghi rõ `Kỳ: #00001`, ngày 20/07/2016, sáu số
**02, 17, 33, 37, 38, 45**. Parser yêu cầu tiêu đề Mega 6/45, ngày trong tiêu đề
khối khớp ngày trên URL, mã kỳ rõ ràng và đúng sáu số hợp lệ. URL theo ngày dùng
mẫu thực tế đã quan sát `xs-mega-ngay-DD-MM-YYYY.html`.

Đối với một khối Minh Ngọc thiếu mã kỳ, collector tải trang Việt Mỹ cùng ngày.
Chỉ khi sáu số khớp giữa hai nguồn mới nhập mã kỳ lấy từ Việt Mỹ và gán nhãn
`cross_checked`, nguồn `xosovietmy+minhngoc`. Hai nguồn bất đồng được ghi thành
`conflict` và không tự ghi đè dữ liệu.

## Lưu ý khi so sánh nguồn

Kết quả máy tìm kiếm được xem là đầu mối tra cứu, không phải dữ liệu nhập. Khi
khảo sát, bản trích tìm kiếm của trang Minh Ngọc riêng Chủ nhật có kỳ #01571
ngày 04/10/2026 khác HTML tải trực tiếp từ trang chính. Đối chiếu trực tiếp Việt Mỹ
ngày 04/10/2026 đã xác nhận dãy trong DB và trang chính cùng là
**15, 20, 29, 37, 40, 45**. Báo cáo `artifacts/crosschecks.json` cũng xác nhận
mẫu kỳ #00001, #00787 và #01575. Không dùng trích tìm kiếm để sửa dữ liệu.

`cross_checked` có nghĩa là hai nguồn thứ cấp khớp nhau, không phải xác minh
trực tiếp bằng thông báo chính thức Vietlott. Các fixture là ảnh chụp HTML thời
điểm kiểm tra để phát hiện thay đổi parser; chúng không thay thế việc lấy dữ liệu
mới khi chạy collector.
