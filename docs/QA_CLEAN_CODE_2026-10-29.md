# DermaScan AI — Báo cáo QA & Clean Code đợt 1

Ngày kiểm tra: **29/10/2026**. Tất cả kết quả trong báo cáo được thực thi mới từ mã nguồn hiện tại; không kế thừa coverage hoặc kết luận kiểm thử cũ.

## 1. Phạm vi và an toàn dữ liệu

- Repository: `LePhanHieu/Test3`.
- Mốc gốc: `main` tại `ba02d6adfa31733bec538ce58677ed2d780af851`.
- Nhánh làm việc: `qa/fresh-baseline-20261029`; **không merge vào main**.
- Các đường dẫn `instance/dermascan_live.db`, `instance/cache.db`, ảnh upload, Grad-CAM và báo cáo PDF **đang được Git theo dõi**. Đã kiểm tra diff: không file nào trong `instance/` bị thay đổi bởi các commit của đợt này.
- Không chạy `test_all_features_e2e.py` nguyên trạng vì script này tạo ca khám, ghi SQLite, upload ảnh và truy cập cache mặc định.
- Test mới chỉ dùng dữ liệu tổng hợp và SQLite trong thư mục tạm; SMTP bị mock chặn, không gọi OpenAI, Redis hoặc AI model thật. Không chạy migration, không xóa file, không thay schema/weights.

## 2. Baseline và kết quả mới

| Hạng mục | Kết quả mới | Giới hạn |
| --- | --- | --- |
| Python syntax | 72/72 file gốc parse thành công | Không thực thi toàn bộ ứng dụng |
| JavaScript syntax | 7/7 file `node --check` đạt | Chưa có browser E2E |
| JavaScript AST sau format | 7/7 tương đương bản gốc | Không thay selector/logic trong JS ngoài |
| Jinja templates | 5/5 parse thành công | Chưa so sánh ảnh chụp trình duyệt |
| HTML structure | 5/5 bảo toàn thứ tự thẻ, ID và biểu thức Jinja | Khoảng trắng giao diện cần visual regression |
| Pytest | **18 passed**, 0 failed | Chỉ các bài test mới và an toàn trong `tests/` |
| Coverage `routes/auth.py` | **45% statement** (409 câu lệnh, thiếu 224) | Chưa phủ hết Auth/API |
| Coverage `services/uncertainty.py` | **100% statement** (11/11) | Không phải coverage AI inference |
| Coverage hai module đo | **47% statement** | Không phải coverage toàn repository |
| Ruff | **131 vấn đề ban đầu → 129 vấn đề còn lại** | Phần lint tồn đọng chưa sửa hàng loạt |
| Bandit | **16 findings: 4 Medium, 12 Low, 0 High** | Chỉ là static scan, không chứng minh ứng dụng an toàn hoàn toàn |

### Định dạng mã nguồn

Đo trên 72 file `.py`, 5 `.html`, 7 `.js` và 7 `.css` có từ commit gốc; không tính file test mới:

| Loại | Trước | Sau | Chênh lệch |
| --- | ---: | ---: | ---: |
| Python | 16.428 dòng | 13.221 dòng | −19,52% |
| HTML/Jinja | 9.623 | 8.952 | −6,97% |
| JavaScript | 6.183 | 6.064 | −1,92% |
| CSS | 10.635 | 10.727 | +0,87% |

Formatter được cấu hình trong `pyproject.toml` (Ruff, 120 ký tự), `.prettierrc.json` (Prettier, 160 ký tự) và `.djlintrc` (Jinja, 140 ký tự). CSS tăng nhẹ do chuẩn hóa bố cục. Python AST giữ nguyên 71/72 file; ngoại lệ là Ruff xóa khoảng trắng cuối dòng trong **docstring** của một migration, không thay đổi lệnh thực thi.

## 3. Công việc đã hoàn tất và bằng chứng

| Module | Thay đổi | Test/kiểm tra | Commit |
| --- | --- | --- | --- |
| Python toàn dự án | Rút gọn biểu thức, lời gọi, căn lề; thêm smoke test không import Flask/AI | `ruff format --check`, Python AST, 3 smoke tests | `50e8b44` |
| JS/CSS | Chuẩn hóa Prettier, giữ `quoteProps` để không đổi AST | JS AST 7/7, `node --check`, Prettier check | `42a9839` |
| HTML/Jinja | Gom thuộc tính cùng dòng khi phù hợp, giữ ID và template logic | Jinja parse 5/5, DOM tags/IDs, Jinja expressions, djLint check | `d96c673` |
| SQLite cache | Cho phép `DERMASCAN_CACHE_DB_PATH` trỏ tới cache thử nghiệm; mặc định vẫn `instance/cache.db` | 2 test đỏ trước sửa → 3 test cache đạt sau sửa | `5d3eaa7` |
| AI uncertainty | Thêm 5 unit test cho phân phối chắc chắn, không chắc chắn, mapping, entropy, one-hot; không sửa thuật toán | 5/5 passed, 100% statement coverage | `bb8587c` |
| Auth/API ba vai trò | Thêm test CSRF, audit log, USER/ADMIN, DOCTOR OTP mock, mã sai, mã đúng, chống replay | 7 integration tests, 18/18 regression suite đạt | `23f3d33` |
| OTP thiếu session ID | Không gọi `db.session.get(User, None)` khi resend/verify thiếu pending user; giữ HTTP 401 và JSON contract | Test cảnh báo SQLAlchemy đỏ trước sửa → đạt sau sửa | `23f3d33` |

File sản xuất thay đổi có logic (ngoài format):

1. `skin_cancer/webapp/services/result_cache.py` — cho phép cấu hình đường dẫn cache cô lập.
2. `skin_cancer/webapp/routes/auth.py` — tránh truy vấn SQLAlchemy với ID rỗng.

File test mới: `tests/test_format_guard.py`, `tests/test_result_cache_isolation.py`, `tests/test_uncertainty.py`, `tests/test_api_auth_isolation.py`.

## 4. Vấn đề chưa xử lý (ưu tiên tiếp theo)

| Ưu tiên | Vấn đề | Đường dẫn | Trạng thái |
| --- | --- | --- | --- |
| P0 | Database, cache và ảnh/báo cáo có thể chứa dữ liệu nhạy cảm đang được Git theo dõi | `instance/` | Chưa xóa hoặc thay Git history; cần phê duyệt riêng |
| P0 | Script E2E cũ tự ghi vào thư mục dự án; chưa cô lập upload/report/Grad-CAM | `test_all_features_e2e.py`, `tasks.py`, `config.py` | Không chạy nguyên trạng; cần thiết kế test harness mới |
| P1 | Exception handler trả `error=str(error)`, có nguy cơ lộ thông tin nội bộ | `skin_cancer/webapp/bootstrap.py` | Cần test contract và xử lý an toàn |
| P1 | Module báo cáo Admin dùng số liệu cố định thay cho thống kê thực | `skin_cancer/webapp/templates/admin.html` | Chưa sửa logic UI do thiếu visual regression/backend thống kê xác minh |
| P2 | Khi Analysis đã `COMPLETED` nhưng cache/queue mất kết quả, API có thể trả `PROCESSING` | `skin_cancer/webapp/routes/analysis_status.py` | Cần test integration trước khi sửa API |
| P2 | Nút PDF/Excel và bộ lọc báo cáo Admin chưa nối xử lý | `skin_cancer/webapp/templates/admin.html` | Chưa sửa; không suy diễn API mới |
| P2 | Chart.js CDN mất kết nối có thể làm timeline lỗi | `skin_cancer/webapp/static/js/timeline.js` | Chưa có browser test |
| P2 | Một số file/hàm dài và xử lý exception quá rộng | `services/report_service.py`, `services/measurement_service.py`, các route/service | Chờ test bảo vệ hành vi |
| P3 | Ruff 129 phát hiện còn tồn đọng | Toàn backend | Chia từng module, không auto-fix hàng loạt |

Bandit Medium gồm `B614` ở `app.py`/`scripts/export_onnx.py` (deserialization checkpoint) và `B104` tại địa chỉ host `0.0.0.0`. Phải xác minh trust boundary và môi trường triển khai trước khi đổi.

## 5. Phần chưa thể xác nhận

- Chưa chạy model Torch/EfficientNet-B0 thực, ONNX, Grad-CAM, so sánh xác suất AI hoặc test tăng tốc bằng GPU.
- Chưa chạy Batch upload, OpenCV đo vùng tổn thương, CSV/Excel/PDF, email report và các luồng transaction phức tạp.
- Chưa có Playwright screenshots trước/sau hay responsive test ở 320/375/390/768/1024/1440 px: browser binary chưa sẵn, full Flask UI phụ thuộc model AI lúc import.
- Chưa test Redis/Celery worker thực; không gửi SMTP thật.
- Chưa đo coverage toàn repository. Chưa thể kết luận dự án đã được kiểm thử toàn diện hay sẵn sàng production.

## 6. Lệnh tái kiểm tra trong môi trường QA đã cài dependencies

```bash
PYTHONDONTWRITEBYTECODE=1 python -B -m pytest -q -s tests -p no:cacheprovider
ruff format --check .
prettier --check 'skin_cancer/webapp/static/js/*.js' 'skin_cancer/webapp/static/css/*.css'
djlint skin_cancer/webapp/templates --check --profile jinja --indent 2 --max-line-length 140 --max-attribute-length 140
ruff check --statistics skin_cancer/webapp tests
bandit -r skin_cancer/webapp
```

Lưu ý: các test trong `tests/` tự tạo SQLite tạm; **không chạy** `test_all_features_e2e.py` cũ trên database thật. Các cấu hình bảo vệ dữ liệu cần giữ nguyên khi mở rộng bộ test.

## 7. Quy tắc bàn giao

Tất cả thay đổi ở nhánh `qa/fresh-baseline-20261029`; không merge, không xóa file, không migration. Kiểm tra `git diff ba02d6a --name-only -- instance` cho kết quả rỗng. Các công việc UI và backend còn lại cần tiếp tục theo từng module cùng test bảo vệ mới.

### Đối chiếu commit GitHub

Nhánh QA được xuất bản lên GitHub bằng các commit tái tạo qua kết nối được cấp quyền; vì vậy **SHA commit remote khác SHA commit local**, nhưng SHA tree (toàn bộ nội dung file và mode) đã được đối chiếu khớp tại từng mốc:

| Commit local | Commit tương ứng trên GitHub |
| --- | --- |
| `50e8b44` | `c5df8d8a21459f0cac715cde2347502142bec1a1` |
| `42a9839` | `b1c463fd0ccab4b313168aff1bae757a412eea2c` |
| `d96c673` | `44312f0ba39c060a0421f135f4d62338e22d03d9` |
| `5d3eaa7` | `ffda7e2c38e0a60ef4d531b14f53f53eb9353e1b` |
| `bb8587c` | `8b16b55f4da7b53fcc17bab9bc31feb8447b92db` |
| `23f3d33` | `efe10ee6d07f356af704d459ddc180d1b6b5858a` |
| `4c0b684` | `adeb4fb1d34a79ae2ca0c28f19d0142ef2de29fb` |

GitHub branch: `https://github.com/LePhanHieu/Test3/tree/qa/fresh-baseline-20261029`. Không merge vào `main`.
