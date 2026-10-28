## 1. Cài đặt – chạy tại thư mục gốc sau giải nén

Khuyến nghị Python 3.11 hoặc 3.12. Môi trường kiểm thử thực tế: Python 3.12.14.

Windows CMD:

```bat
python -m venv .venv
.venv\Scripts\activate
python -m pip install -r requirements-test.txt
python -m pip install -r requirements.txt
python -m pip install -r requirements-database.txt
copy .env.example .env
python -c "import secrets; print(secrets.token_hex(32))"
```

Dán chuỗi vừa sinh vào `SECRET_KEY` trong `.env`. Các giá trị khác cho demo cục bộ:

```dotenv
SECRET_KEY=<chuỗi ngẫu nhiên vừa sinh>
ALLOW_DEMO_SEED=true
DEMO_PASSWORD=<mật khẩu demo tự chọn dài 12–256 ký tự>
SESSION_COOKIE_SECURE=false
```

Linux/macOS: thay lệnh activate bằng `source .venv/bin/activate` và copy bằng `cp .env.example .env`.

## 2. Kiểm tra

```bat
python -m flask --app skin_cancer.webapp.database_app db upgrade
python -m flask --app skin_cancer.webapp.database_app db current
python -m flask --app skin_cancer.webapp.database_app db check
python -m flask --app skin_cancer.webapp.database_app seed-demo
python -m pytest -q
```

Database mặc định: `instance/dermascan.db`, tính theo thư mục source, không phụ thuộc nơi gọi chương trình. Có thể đặt `DATABASE_URL` thành URL SQLite tuyệt đối trong `.env`, ví dụ `sqlite:////absolute/path/to/instance/dermascan.db`. Thư mục cha của đường dẫn tùy chọn phải tồn tại.

Sau này có thay đổi models:

```bat
python -m flask --app skin_cancer.webapp.database_app db migrate -m "Mo ta thay doi schema"
python -m flask --app skin_cancer.webapp.database_app db upgrade
```

## 4. Tài khoản demo

| Email                    | Role   |
| ------------------------ | ------ |
| admin@dermascan.local    | ADMIN  |
| doctor@dermascan.local   | DOCTOR |
| patient@dermascan.local  | USER A |
| patient2@dermascan.local | USER B |
