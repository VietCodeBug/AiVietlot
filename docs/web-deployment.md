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

Đã push bản giao diện đầy đủ lên [VietCodeBug/AiVietlot](https://github.com/VietCodeBug/AiVietlot). Commit triển khai đầu tiên `d89d09a` đã đạt [Web checks](https://github.com/VietCodeBug/AiVietlot/actions/runs/38661586653) và [Collector checks](https://github.com/VietCodeBug/AiVietlot/actions/runs/38661586639) trên GitHub.

Đã đăng nhập **Vercel CLI 64.1.0 trong CMD** với tài khoản `phamhoainam1709`, tạo project `mega-lab` trong scope Hobby `phamhoainam1709s-projects`, đặt Root Directory=`web`, Vite, Node 24.x. CLI đã xác nhận kết nối repo GitHub bằng `vercel git connect`.

- Production: **https://mega-lab-iota.vercel.app**.
- [Deployment đầu tiên](https://vercel.com/phamhoainam1709s-projects/mega-lab/6hCPhC3PTKKQw5vp6RbvMZqdnNz7) đã READY; URL production trả HTTP 200 không cần đăng nhập Vercel.
- Hai cấu hình công khai `VITE_SUPABASE_URL` và `VITE_SUPABASE_PUBLISHABLE_KEY` đã đặt qua stdin cho production/preview/development. Không đưa secret backend lên Vercel.
- Playwright kiểm tra chính production, gồm dữ liệu Supabase thật, báo cáo phân tích thật, điện thoại 360/390px và reload offline; báo cáo tại `artifacts/web-qa/report.json`.
- Không bật dịch vụ trả phí, nâng gói hoặc thay đổi billing.

## Lệnh CMD sau khi đã liên kết

```bat
npx --yes vercel@64.1.0 whoami
npx --yes vercel@64.1.0 project inspect mega-lab --scope phamhoainam1709s-projects
git push origin main
```

Push lên `main` sẽ kích hoạt Git integration của Vercel. Nếu cần deploy thủ công từ máy này:

```bat
.venv\Scripts\python.exe scripts\deploy_vercel.py
```

Helper dùng CMD Vercel CLI và một bản copy sạch từ commit HEAD, tránh upload virtualenv,
test temp, `.env` và artifacts local. Nó giữ Root Directory=`web`, chỉ copy project ID từ
`.vercel/project.json`, dùng phiên CLI đã đăng nhập. `scripts/configure_vercel_public_env.py`
chỉ gửi hai biến publishable từ `web/.env.local` qua stdin, không gửi secret backend.

Collector cron dùng GitHub Actions Secrets riêng. Ngày 15/10/2026, người dùng đã xác nhận
cho phép dùng key hiện tại để bật cloud sync; đã cấu hình hai Secrets SUPABASE_URL và
SUPABASE_SECRET_KEY bằng mã hóa public key của GitHub, không đưa vào repo/VITE.
Luồng nghiên cứu theo kỳ và các phép kiểm tra được mô tả tại [prospective-research.md](prospective-research.md).
