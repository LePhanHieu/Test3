from datetime import datetime, timedelta
import hashlib
import secrets
import sys
import traceback
from flask import Blueprint, current_app, request, jsonify, session, abort, redirect, render_template
from flask_login import current_user, login_user, logout_user
from flask_mail import Message
from flask_wtf.csrf import generate_csrf
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from werkzeug.exceptions import HTTPException
from ..extensions import db, limiter, login_manager, csrf, mail
from ..models import User, AuditLog, DoctorApplication, SecuritySetting
from ..models.base import utcnow
from ..services.access import require_roles
from ..services.user_deletion import delete_unrelated_user, deletable_certificate, cleanup_doctor_certificate

bp = Blueprint('auth', __name__, url_prefix='/api/auth')

SAMPLE_DOCTOR_EMAIL = 'doctor@dermascan.local'


def _hash_token(value):
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _audit(email, event, success, user=None):
    db.session.add(AuditLog(
        email=email,
        event=event,
        success=success,
        user_id=user.id if user else None,
        ip_address=request.remote_addr,
        user_agent=request.headers.get("User-Agent", "")[:500],
    ))


def _mask_phone(phone):
    digits = "".join(char for char in (phone or "") if char.isdigit())
    if len(digits) < 7:
        return phone or ""
    return f"{digits[:2]}{'*' * (len(digits) - 6)}{digits[-4:]}"


def _print_terminal(message):
    """In ra Terminal ma khong vang UnicodeEncodeError (cp1252/cp1258 tren Windows).

    Mot print tieng Viet bi loi ma hoa se lam saph nguyen request -> HTTP 500,
    nen moi output OTP/xac thuc email deu di qua day.
    """
    try:
        print(message, flush=True)
    except UnicodeEncodeError:
        encoding = getattr(sys.stdout, "encoding", None) or "utf-8"
        safe = message.encode(encoding, errors="replace").decode(encoding)
        print(safe, flush=True)


def _create_and_log_otp(user):
    otp_code = f"{secrets.randbelow(1000000):06d}"
    user.two_factor_code_hash = _hash_token(otp_code)
    user.two_factor_code_expires_at = utcnow() + timedelta(minutes=5)
    _print_terminal("\n==================================================")
    _print_terminal(f" [DERMASCAN AI - 2FA SYSTEM] Mã OTP của tài khoản {user.email} là: {otp_code}")
    _print_terminal("==================================================\n")
    return otp_code


def _doctor_email_otp_required(user):
    """Only approved, registered doctors receive an email OTP at each login."""
    return (
        user.role == 'DOCTOR'
        and user.email != SAMPLE_DOCTOR_EMAIL
        and db.session.scalar(
            db.select(DoctorApplication.status).where(DoctorApplication.user_id == user.id)
        ) == 'APPROVED'
    )


def _requires_login_otp(user):
    if user.role == 'DOCTOR' and user.email == SAMPLE_DOCTOR_EMAIL:
        return False
    return _doctor_email_otp_required(user) or user.two_factor_enabled or _admin_2fa_required(user)


def _email_hint(email):
    name, separator, domain = email.partition('@')
    return f"{name[:1]}***@{domain}" if separator else '***'


def _issue_login_otp(user):
    """Send approved doctors' OTP through configured SMTP; other roles keep existing 2FA."""
    if not _doctor_email_otp_required(user):
        _create_and_log_otp(user)
        return 'Mã xác thực đã được tạo. Vui lòng lấy OTP trong cửa sổ Terminal để tiếp tục.'

    if not all(current_app.config.get(key) for key in (
        'MAIL_SERVER', 'MAIL_USERNAME', 'MAIL_PASSWORD', 'MAIL_DEFAULT_SENDER'
    )):
        raise RuntimeError('SMTP chưa được cấu hình đầy đủ.')

    otp = f"{secrets.randbelow(1000000):06d}"
    user.two_factor_code_hash = _hash_token(otp)
    user.two_factor_code_expires_at = utcnow() + timedelta(minutes=5)
    mail.send(Message(
        subject='DermaScan AI - Mã xác thực đăng nhập bác sĩ',
        recipients=[user.email],
        html=render_template('emails/doctor_otp.html', USER_NAME=user.full_name, OTP_CODE=otp),
        body=(
            f'Mã OTP đăng nhập DermaScan AI của bạn là: {otp}\n'
            'Mã có hiệu lực trong 5 phút và chỉ sử dụng một lần.\n'
            'Nếu bạn không đăng nhập, hãy bỏ qua email này.'
        ),
    ))
    return f'Mã OTP 6 chữ số đã được gửi đến {_email_hint(user.email)}.'

def _issue_token(user, kind, minutes=30):
    token = secrets.token_urlsafe(32)
    setattr(user, f"{kind}_token_hash", _hash_token(token))
    setattr(user, f"{kind}_expires_at", utcnow() + timedelta(minutes=minutes))
    return token


def _security_setting():
    setting = db.session.get(SecuritySetting, 1)
    if setting is None:
        setting = SecuritySetting(id=1)
        db.session.add(setting)
        db.session.flush()
    return setting


def _admin_2fa_required(user):
    setting = _security_setting()
    return user.role == "ADMIN" and setting.require_admin_2fa


@login_manager.user_loader
def load_user(user_id):
    try:
        user = db.session.get(User, int(user_id))
    except (TypeError, ValueError):
        return None
    return user if user and user.is_active and user.deleted_at is None else None


@login_manager.unauthorized_handler
def unauthorized():
    return jsonify(success=False, message='Cần đăng nhập'), 401


def public_user(user):
    return {
        'id': user.id,
        'full_name': user.full_name,
        'email': user.email,
        'role': user.role,
        'phone': user.phone,
        'gender': user.gender,
        'date_of_birth': user.date_of_birth.isoformat() if user.date_of_birth else None,
        'avatar_url': user.avatar_url,
        'email_verified': user.email_verified,
        'two_factor_enabled': user.two_factor_enabled,
    }


def role_redirect(role):
    return {
        'ADMIN': '/admin',
        'DOCTOR': '/doctor',
        'USER': '/patient',
    }.get(role, '/')


def login_response(user):
    return jsonify(
        success=True,
        role=user.role,
        redirect_url=role_redirect(user.role),
        user=public_user(user),
    )


@bp.get('/csrf')
def get_csrf():
    return jsonify(csrf_token=generate_csrf())


@bp.post('/login')
@limiter.limit(
    lambda: current_app.config["RATELIMIT_LOGIN"]
)
def login():
    payload = request.get_json(silent=True)
    if not isinstance(payload, dict):
        abort(400)
    email, password = payload.get('email'), payload.get('password')
    if not isinstance(email,str) or not isinstance(password,str) or len(email)>254 or len(password)>256:
        abort(400)
    user = db.session.scalar(db.select(User).where(User.email == email.strip().lower()))
    if not user or user.deleted_at is not None or not user.is_active or not user.check_password(password):
        _audit(email.strip().lower() if isinstance(email, str) else "", "LOGIN", False, user)
        db.session.commit()
        return jsonify(success=False, message='Email hoặc mật khẩu không hợp lệ'), 401
    if not user.email_verified and not _doctor_email_otp_required(user):
        return jsonify(success=False, message="Vui lòng xác thực email trước khi đăng nhập."), 403
    if _requires_login_otp(user):
        session.clear()
        try:
            message = _issue_login_otp(user)
            db.session.commit()
        except Exception:
            db.session.rollback()
            current_app.logger.exception("Failed to dispatch login OTP")
            return jsonify(success=False, message="Không gửi được OTP. Vui lòng thử lại sau."), 503
        session["pending_2fa_user_id"] = user.id
        return jsonify(success=True, requires_2fa=True, message=message)
    session.clear()
    login_user(user, remember=False, fresh=True)
    session['role'] = user.role
    _audit(user.email, "LOGIN", True, user)
    db.session.commit()
    return login_response(user)


@bp.post('/admin/login')
@limiter.limit(
    lambda: current_app.config["RATELIMIT_LOGIN"]
)
def admin_login():
    """Authenticate an administrator for the Admin Portal."""
    payload = request.get_json(silent=True)
    if not isinstance(payload, dict):
        abort(400)

    email = payload.get('email', payload.get('username'))
    password = payload.get('password')
    if (
        not isinstance(email, str)
        or not isinstance(password, str)
        or not 1 <= len(email.strip()) <= 254
        or not 1 <= len(password) <= 256
    ):
        return jsonify(success=False, message='Sai tài khoản hoặc mật khẩu'), 401

    user = db.session.scalar(
        db.select(User).where(User.email == email.strip().lower())
    )
    if user is None or user.deleted_at is not None or not user.is_active or not user.check_password(password):
        _audit(email.strip().lower() if isinstance(email, str) else "", "ADMIN_LOGIN", False, user)
        db.session.commit()
        return jsonify(success=False, message='Sai tài khoản hoặc mật khẩu'), 401
    if not user.email_verified:
        return jsonify(success=False, message="Vui lòng xác thực email trước khi đăng nhập."), 403
    if user.role != 'ADMIN':
        return jsonify(
            success=False,
            message='Tài khoản không có quyền quản trị',
        ), 403

    if _requires_login_otp(user):
        _create_and_log_otp(user)
        db.session.commit()
        session.clear()
        session["pending_2fa_user_id"] = user.id
        return jsonify(success=True, requires_2fa=True, message="Mã xác thực đã được tạo. Vui lòng lấy OTP trong cửa sổ Terminal để tiếp tục.")
    session.clear()
    login_user(user, remember=False, fresh=True)
    session['role'] = user.role
    _audit(user.email, "ADMIN_LOGIN", True, user)
    db.session.commit()
    return login_response(user)


@bp.post('/resend-2fa')
@limiter.limit("3 per minute")
def resend_two_factor():
    """Issue a fresh OTP only for the account with a pending 2FA login."""
    user = db.session.get(User, session.get("pending_2fa_user_id"))
    if (
        not user
        or user.deleted_at is not None
        or not user.is_active
        or (not user.email_verified and not _doctor_email_otp_required(user))
        or not _requires_login_otp(user)
    ):
        return jsonify(success=False, message="Phiên xác thực 2 lớp không hợp lệ. Vui lòng đăng nhập lại."), 401

    try:
        message = _issue_login_otp(user)
        db.session.commit()
    except Exception:
        db.session.rollback()
        current_app.logger.exception("Failed to resend login OTP")
        return jsonify(success=False, message="Không gửi được OTP. Vui lòng thử lại sau."), 503
    return jsonify(success=True, message=message)


@bp.post('/verify-2fa')
@limiter.limit("5 per minute")
def verify_two_factor():
    payload = request.get_json(silent=True) or {}
    code = str(payload.get("code", "")).strip()
    user = db.session.get(User, session.get("pending_2fa_user_id"))
    if not user or user.deleted_at is not None or not user.is_active or not _requires_login_otp(user) or not user.two_factor_code_expires_at:
        return jsonify(success=False, message="Phiên xác thực 2 lớp không hợp lệ."), 401
    if user.two_factor_code_expires_at < utcnow() or not secrets.compare_digest(
        user.two_factor_code_hash or "", _hash_token(code)
    ):
        _audit(user.email, "2FA_LOGIN", False, user)
        db.session.commit()
        return jsonify(success=False, message="Mã xác thực không đúng hoặc đã hết hạn."), 401
    session.clear()
    login_user(user, remember=False, fresh=True)
    session["role"] = user.role
    if _doctor_email_otp_required(user):
        # Successful email delivery + OTP possession proves mailbox access.
        user.email_verified = True
    user.two_factor_code_hash = None
    user.two_factor_code_expires_at = None
    _audit(user.email, "2FA_LOGIN", True, user)
    db.session.commit()
    return login_response(user)


@bp.route('/logout', methods=['GET', 'POST'])
@csrf.exempt
def logout():
    """Đăng xuất an toàn cho mọi vai trò (Doctor, User, v.v.), xóa sạch session và cookie."""
    try:
        if current_user.is_authenticated:
            user = current_user._get_current_object()
            try:
                _audit(user.email, "LOGOUT", True, user)
                db.session.commit()
            except SQLAlchemyError:
                db.session.rollback()
                current_app.logger.exception("Could not persist logout audit event")
            logout_user()
    except Exception:
        pass
    session.clear()

    if request.method == 'GET':
        resp = redirect('/')
    else:
        resp = jsonify(success=True, redirect_url='/')

    cookie_name = current_app.config.get('SESSION_COOKIE_NAME', 'session')
    remember_cookie = current_app.config.get('REMEMBER_COOKIE_NAME', 'remember_token')
    resp.delete_cookie(cookie_name, path='/')
    resp.delete_cookie(remember_cookie, path='/')
    return resp


@bp.route('/admin/logout', methods=['GET', 'POST'])
@csrf.exempt
def admin_logout():
    """End the administrator session and remove all session data and cookies."""
    try:
        if current_user.is_authenticated:
            user = current_user._get_current_object()
            try:
                _audit(user.email, "ADMIN_LOGOUT", True, user)
                db.session.commit()
            except SQLAlchemyError:
                db.session.rollback()
                current_app.logger.exception("Could not persist admin logout audit event")
            logout_user()
    except Exception:
        pass
    session.clear()

    if request.method == 'GET':
        resp = redirect('/')
    else:
        resp = jsonify(success=True, redirect_url='/')

    cookie_name = current_app.config.get('SESSION_COOKIE_NAME', 'session')
    remember_cookie = current_app.config.get('REMEMBER_COOKIE_NAME', 'remember_token')
    resp.delete_cookie(cookie_name, path='/')
    resp.delete_cookie(remember_cookie, path='/')
    return resp


@bp.get('/admin/me')
@require_roles('ADMIN')
def admin_me():
    return jsonify(public_user(current_user))


@bp.get('/me')
@require_roles()
def me():
    return jsonify(public_user(current_user))


@bp.put('/profile')
@require_roles()
def update_profile():
    payload = request.get_json(silent=True)
    if not isinstance(payload, dict):
        abort(400)
    
    full_name = payload.get('full_name')
    if full_name is not None:
        if not isinstance(full_name, str) or not (2 <= len(full_name.strip()) <= 150):
            return jsonify(success=False, message='Họ tên không hợp lệ (2-150 ký tự).'), 400
        current_user.full_name = full_name.strip()
    
    phone = payload.get('phone')
    if phone is not None:
        phone_str = str(phone).strip() if phone else None
        if phone_str and len(phone_str) > 30:
            return jsonify(success=False, message='Số điện thoại không hợp lệ.'), 400
        current_user.phone = phone_str
    if 'avatar_url' in payload:
        avatar = payload.get('avatar_url')
        if avatar and (not isinstance(avatar, str) or len(avatar) > 500):
            return jsonify(success=False, message='Avatar không hợp lệ.'), 400
        current_user.avatar_url = avatar or None
    if 'two_factor_enabled' in payload:
        enabled = bool(payload.get('two_factor_enabled'))
        if current_user.role == "ADMIN" and _security_setting().require_admin_2fa and not enabled:
            return jsonify(success=False, message="Chính sách hệ thống yêu cầu Admin bật 2FA."), 400
        current_user.two_factor_enabled = enabled
        
    gender = payload.get('gender')
    if gender is not None:
        gender_str = str(gender).strip() if gender else None
        if gender_str and len(gender_str) > 30:
            return jsonify(success=False, message='Giới tính không hợp lệ.'), 400
        current_user.gender = gender_str
        
    dob = payload.get('date_of_birth')
    if dob is not None:
        if dob:
            from datetime import date
            try:
                current_user.date_of_birth = date.fromisoformat(str(dob).strip())
            except (ValueError, TypeError):
                return jsonify(success=False, message='Ngày sinh không đúng định dạng YYYY-MM-DD.'), 400
        else:
            current_user.date_of_birth = None
            
    _audit(current_user.email, "PROFILE_UPDATED", True, current_user)
    db.session.commit()
    return jsonify(success=True, user=public_user(current_user))


@bp.post('/change-password')
@require_roles()
def change_password():
    payload = request.get_json(silent=True) or {}
    old_password = payload.get("current_password")
    new_password = payload.get("new_password")
    minimum = _security_setting().password_min_length
    if not current_user.check_password(old_password):
        return jsonify(success=False, message="Mật khẩu hiện tại không đúng."), 400
    if not isinstance(new_password, str) or len(new_password) < minimum:
        return jsonify(success=False, message=f"Mật khẩu mới phải có ít nhất {minimum} ký tự."), 400
    current_user.set_password(new_password)
    _audit(current_user.email, "PASSWORD_CHANGED", True, current_user)
    db.session.commit()
    return jsonify(success=True)


@bp.post('/forgot-password')
@limiter.limit("5 per minute")
def forgot_password():
    payload = request.get_json(silent=True) or {}
    email = str(payload.get("email", "")).strip().lower()
    user = db.session.scalar(db.select(User).where(User.email == email))
    if user and user.deleted_at is None and user.is_active:
        otp_code = f"{secrets.randbelow(1000000):06d}"
        user.password_reset_token_hash = _hash_token(otp_code)
        user.password_reset_expires_at = utcnow() + timedelta(minutes=5)
        db.session.commit()
        _print_terminal("\n==================================================")
        _print_terminal(f" [DERMASCAN AI - PASSWORD RESET] Mã OTP của tài khoản {user.email} là: {otp_code}")
        _print_terminal("==================================================\n")
    return jsonify(success=True, message="Nếu email tồn tại, mã OTP đặt lại mật khẩu đã được tạo và hiển thị trong Terminal.")


@bp.post('/reset-password')
@limiter.limit("5 per minute")
def reset_password():
    payload = request.get_json(silent=True) or {}
    token = str(payload.get("token", "")).strip()
    password = payload.get("new_password")
    user = db.session.scalar(db.select(User).where(User.password_reset_token_hash == _hash_token(token)))
    if not user or not user.password_reset_expires_at or user.password_reset_expires_at < utcnow():
        return jsonify(success=False, message="Mã OTP đặt lại mật khẩu không hợp lệ hoặc đã hết hạn. Hãy yêu cầu mã mới."), 400
    if not isinstance(password, str) or len(password) < _security_setting().password_min_length:
        return jsonify(success=False, message="Mật khẩu mới chưa đủ mạnh."), 400
    user.set_password(password)
    user.password_reset_token_hash = None
    user.password_reset_expires_at = None
    user.two_factor_code_hash = None
    user.two_factor_code_expires_at = None
    _audit(user.email, "PASSWORD_RESET", True, user)
    db.session.commit()
    return jsonify(success=True)

@bp.post('/verify-email')
def verify_email():
    token = request.get_json(silent=True).get("token", "") if request.is_json else request.args.get("token", "")
    user = db.session.scalar(db.select(User).where(User.email_verification_token_hash == _hash_token(str(token))))
    if not user or not user.email_verification_expires_at or user.email_verification_expires_at < utcnow():
        return jsonify(success=False, message="Mã xác thực email không hợp lệ hoặc đã hết hạn."), 400
    user.email_verified = True
    if user.role != "DOCTOR" or user.doctor_application is None:
        user.is_active = True
    user.email_verification_token_hash = None
    user.email_verification_expires_at = None
    _audit(user.email, "EMAIL_VERIFIED", True, user)
    db.session.commit()
    return jsonify(success=True, message="Email đã được xác thực.")


@bp.post('/register')
@limiter.limit(
    lambda: current_app.config["RATELIMIT_LOGIN"]
)
def register():
    payload = request.get_json(silent=True)
    if not isinstance(payload, dict):
        abort(400)

    full_name = payload.get('full_name')
    email = payload.get('email')
    password = payload.get('password')
    role = payload.get('role', 'USER')

    if not isinstance(full_name, str) or not (2 <= len(full_name.strip()) <= 150):
        return jsonify(
            success=False,
            message='Họ tên không hợp lệ (2-150 ký tự).',
        ), 400

    if not isinstance(email, str) or not (3 <= len(email.strip()) <= 254) or '@' not in email:
        return jsonify(success=False, message='Email không hợp lệ.'), 400

    # User.set_password yêu cầu 12-256 ký tự
    if not isinstance(password, str) or not (12 <= len(password) <= 256):
        return jsonify(
            success=False,
            message='Mật khẩu phải có 12–256 ký tự',
        ), 400

    # Không cho phép tự đăng ký quyền ADMIN
    if role not in ('DOCTOR', 'USER'):
        role = 'USER'

    existing = db.session.scalar(
        db.select(User).where(User.email == email.strip().lower())
    )
    old_certificate = None
    if existing:
        if existing.deleted_at is None:
            return jsonify(success=False, message='Email đã được sử dụng.'), 409
        old_certificate = deletable_certificate(existing)
        blocker = delete_unrelated_user(existing)
        if blocker:
            return jsonify(success=False, message='Email thuộc tài khoản cũ có dữ liệu cần lưu giữ. Vui lòng liên hệ quản trị viên.'), 409

    try:
        user = User(
            email=email.strip(),
            full_name=full_name.strip(),
            role=role,
            is_active=False,
            email_verified=False,
        )
        user.set_password(password)
    except ValueError as error:
        return jsonify(success=False, message=str(error)), 400

    db.session.add(user)
    if role == "DOCTOR":
        db.session.add(DoctorApplication(user=user, status="PENDING"))
    verification_token = _issue_token(user, "email_verification", 24) if role != "DOCTOR" else None
    try:
        db.session.commit()
    except IntegrityError:
        db.session.rollback()
        return jsonify(success=False, message='Email đã được sử dụng.'), 409

    cleanup_doctor_certificate(old_certificate)
    if verification_token:
        _print_terminal("\n==================================================")
        _print_terminal(f" [DERMASCAN AI - EMAIL VERIFICATION] Mã xác thực của tài khoản {user.email} là: {verification_token}")
        _print_terminal("==================================================\n")
    return jsonify(
        success=True,
        user=public_user(user),
        verification_required=role != "DOCTOR",
        approval_required=role == "DOCTOR",
    ), 201