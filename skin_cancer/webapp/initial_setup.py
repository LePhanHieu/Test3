"""One-time initialization for a fresh local DermaScan database.

This is not a demo seed: it never creates patient cases or analysis results.
"""

import click
from sqlalchemy.exc import IntegrityError

from .extensions import db
from .models import Case, SiteSetting, Slide, User
from .services.site_settings_service import SiteSettingsService


INITIAL_SLIDES = (
    {
        "title": "Kiến thức về ung thư da",
        "subtitle": "Nhận biết sớm các dấu hiệu bất thường trên da.",
        "image_path": "skin_cancer/webapp/assets/demoslide1.png",
        "button_text": "Tìm hiểu ngay",
        "button_url": "https://www.aad.org/public/diseases/skin-cancer",
    },
    {
        "title": "Tìm hiểu các bệnh lý da",
        "subtitle": "Khám phá kiến thức y khoa về tổn thương da.",
        "image_path": "skin_cancer/webapp/assets/demoslide2.png",
        "button_text": "Xem chi tiết",
        "button_url": "https://dermnetnz.org/topics/skin-cancer",
    },
)

LOCAL_STARTER_PASSWORD = "123456123456"  # Local development only; never use in production.
LOCAL_STARTER_ACCOUNTS = {
    "ADMIN": ("Quản trị viên", "admin@dermascan.local", LOCAL_STARTER_PASSWORD),
    "DOCTOR": ("Bác sĩ", "doctor@dermascan.local", LOCAL_STARTER_PASSWORD),
    "USER": ("Người dùng A", "patient@dermascan.local", LOCAL_STARTER_PASSWORD),
}
LEGACY_DEMO_EMAILS = frozenset({
    "admin@dermascan.local", "doctor@dermascan.local",
    "patient@dermascan.local", "patient2@dermascan.local",
})


def _already_initialized():
    """Refuse partial/legacy databases, but allow a safe repeated startup."""
    users = db.session.scalars(db.select(User)).all()
    if not users:
        return False

    if db.session.scalar(db.select(Case.id).where(Case.case_code.like("DEMO-%"))):
        raise click.ClickException(
            "Database đang chứa dữ liệu demo; hãy chọn SQLite mới qua DATABASE_URL."
        )

    existing_emails = {user.email for user in users}
    # Legacy seed contained exactly four known demo emails, while a legitimate
    # database can accumulate any number of registered doctors/patients.
    # Never infer "demo database" from a user count greater than three.
    if existing_emails == LEGACY_DEMO_EMAILS:
        raise click.ClickException(
            "Database đang chứa dữ liệu demo; hãy chọn SQLite mới qua DATABASE_URL."
        )

    # Existing content is operator-managed. A later account lock or banner
    # deletion must not stop the site or silently recreate anything.
    has_admin = any(user.role == "ADMIN" for user in users)
    if has_admin and db.session.get(SiteSetting, 1) is not None:
        return True

    raise click.ClickException(
        "Database đã có tài khoản nhưng chưa được thiết lập đầy đủ; "
        "không ghi đè dữ liệu. Hãy kiểm tra DATABASE_URL."
    )


def provision_initial_data(accounts, *, allow_local_starter_emails=False):
    """Create the three owner-specified users and existing branding atomically."""
    if set(accounts) != {"ADMIN", "DOCTOR", "USER"}:
        raise ValueError("Cần đủ ba vai trò ADMIN, DOCTOR và USER.")
    if db.session.scalar(db.select(User.id).limit(1)) is not None:
        raise ValueError("Database đã có tài khoản; không được tạo đè.")

    created = {}
    try:
        for role in ("ADMIN", "DOCTOR", "USER"):
            name, email, password = accounts[role]
            if not isinstance(name, str) or not 2 <= len(name.strip()) <= 150:
                raise ValueError(f"Họ tên {role} phải có 2–150 ký tự.")
            if isinstance(email, str) and email.strip().lower() in LEGACY_DEMO_EMAILS:
                if not (allow_local_starter_emails and email.strip().lower() == LOCAL_STARTER_ACCOUNTS[role][1]):
                    raise ValueError(f"Email {role} thuộc tài khoản demo cũ; hãy dùng email thật.")
            user = User(
                full_name=name.strip(), email=email, role=role,
                is_active=True, email_verified=True,
            )
            user.set_password(password)
            db.session.add(user)
            created[role] = user

        db.session.flush()

        settings = SiteSettingsService.FALLBACKS
        db.session.add(SiteSetting(id=1, updated_by=created["ADMIN"].id, **settings))
        for position, values in enumerate(INITIAL_SLIDES, start=1):
            db.session.add(Slide(
                **values, display_order=position, is_active=True,
                created_by=created["ADMIN"].id,
            ))
        db.session.commit()
    except Exception:
        db.session.rollback()
        raise


def register_initial_setup(app):
    @app.cli.command("setup-initial")
    @click.option(
        "--local-starter-accounts", is_flag=True,
        help="Tự động tạo 3 tài khoản cố định chỉ dành cho máy phát triển.",
    )
    def setup_initial_command(local_starter_accounts):
        """Provision ADMIN, DOCTOR and USER once on an empty SQLite database."""
        if _already_initialized():
            click.echo("Database đã được thiết lập; giữ nguyên các tài khoản hiện tại.")
            return

        if local_starter_accounts:
            click.echo("CHỈ DÀNH CHO PHÁT TRIỂN: tạo 3 tài khoản cố định, không có ca bệnh demo.")
            accounts = LOCAL_STARTER_ACCOUNTS
        else:
            click.echo("Thiết lập 3 tài khoản thật, không dùng dữ liệu demo.")
            accounts = {}
            for role in ("ADMIN", "DOCTOR", "USER"):
                full_name = click.prompt(f"Họ tên {role}", type=str)
                email = click.prompt(f"Email {role}", type=str)
                password = click.prompt(
                    f"Mật khẩu {role} (12–256 ký tự)",
                    hide_input=True, confirmation_prompt=True,
                )
                accounts[role] = (full_name, email, password)

        try:
            provision_initial_data(accounts, allow_local_starter_emails=local_starter_accounts)
        except IntegrityError as error:
            raise click.ClickException(
                "Email trùng hoặc ràng buộc database không hợp lệ; "
                "không tài khoản nào được tạo."
            ) from error
        except ValueError as error:
            raise click.ClickException(str(error)) from error

        click.echo("Đã tạo ADMIN, DOCTOR, USER và 2 banner; không tạo ca demo.")