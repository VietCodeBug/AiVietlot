# Đưa giao diện Mega Lab lên Vercel

Frontend React/TypeScript/Vite ở `web/`; Python collector và migration vẫn ở repository chung. Vercel phục vụ giao diện, Supabase lưu kết quả, GitHub Actions thu thập kỳ mới. Không chạy Python collector hoặc cron trong tab trình duyệt.

## Cấu hình project

Import repository [VietCodeBug/AiVietlot](https://github.com/VietCodeBug/AiVietlot) trên Vercel sau khi mã đã được push và kiểm tra thành công. Đặt:

| Trường | Giá trị |
| --- | --- |
| Root Directory | `web` |
| Framework Preset | `Vite` |
| Install Command | `npm ci` |
| Build Command | `npm run build` |
| Output Directory | `dist` |
| Node.js | `24.x` |
| Production Branch | `main` |

`web/vercel.json` được đọc từ Root Directory này. Không cần thêm một `vercel.json` khác ở gốc repository. Đường dẫn app được rewrite về `index.html` để mở trực tiếp/reload route; `/assets/` và đường dẫn có đuôi file được giữ riêng để file thiếu trả 404 thay vì HTML. Cách đặt root và SPA dựa trên [cấu hình build Vercel](https://vercel.com/docs/builds/configure-a-build#root-directory) và [hướng dẫn Vite](https://vercel.com/docs/frameworks/frontend/vite#using-vite-to-make-spas).

Trình duyệt chỉ được dùng Supabase publishable key nếu frontend cần kết nối trực tiếp. Không đưa secret key, mật khẩu PostgreSQL, GitHub token hoặc Vercel token vào biến `VITE_*`, file public hoặc mã frontend. Credentials đã từng gửi trong chat phải được thay trước khi lưu vào secrets cloud theo yêu cầu trong tài liệu ban đầu.

## Kiểm tra trước khi push

Chạy từ repository root:

```powershell
npm --prefix web ci
npm --prefix web run lint
npm --prefix web run typecheck
npm --prefix web run test
npm --prefix web run build
```

Workflow [web-ci.yml](../.github/workflows/web-ci.yml) chạy lại các bước này với Node 24 khi mã web thay đổi, không cần credentials Supabase hoặc Vercel. Commit lock file `web/package-lock.json`; không commit `node_modules`, `dist`, `.vercel` hoặc `.env`.

Sau khi Vercel được kết nối GitHub, push lên `main` tạo deployment production, còn nhánh/PR có thể có preview theo cấu hình project. Kiểm tra trạng thái build và URL thực tế trong Vercel; chưa có deployment thành công thì chưa có URL giao diện đã nghiệm thu.

## Kiểm tra deployment

Mở URL production ở điện thoại và desktop; thử reload trực tiếp một route, xem dữ liệu thật, thử retry khi mạng lỗi, và kiểm tra file JS/CSS trả đúng kiểu nội dung. Request `/assets/file-khong-ton-tai.js` phải trả 404. So sánh kỳ mới nhất và nguồn trên giao diện với audit database.

Giữ riêng link GitHub commit, lần chạy Web checks, Vercel deployment và URL production trong hồ sơ nghiệm thu. Collector sync tiếp tục dùng workflows hiện có; frontend deploy không chứng minh rằng lịch nhập dữ liệu đã được bật.

## Trạng thái tài khoản đã kiểm tra ngày 15/10/2026

Git Credential Manager có tài khoản GitHub `VietCodeBug`. Repository public `VietCodeBug/AiVietlot` tồn tại, nhưng tại thời điểm kiểm tra API báo repository rỗng; bản local cũng chưa có commit hoặc remote. Vì vậy trạng thái đó chưa phải một lần push mã thành công.

Vercel CLI 64.1.0 kiểm tra bằng `whoami` báo **Logged out**. Chưa tạo project, chưa kết nối GitHub với Vercel và chưa có deployment/URL Vercel được xác minh. Cần đăng nhập tài khoản Vercel có quyền project để liên kết và deploy; không tạo URL tạm hoặc tự đổi billing.
