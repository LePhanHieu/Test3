"""Admin portal pages and the small set of admin dashboard APIs."""
from datetime import date, datetime, timedelta

from flask import Blueprint, abort, current_app, jsonify, render_template, request, send_from_directory, send_file
from flask_login import current_user
from flask_mail import Message
from sqlalchemy import func, or_
from sqlalchemy.orm import selectinload
from pathlib import Path
from uuid import uuid4
from werkzeug.utils import secure_filename

from ..extensions import db, mail
from ..models import Analysis, AnalysisResult, Case, CaseImage, User, AuditLog, DoctorApplication, SecuritySetting
from ..models.base import utcnow
from ..services.access import require_roles
from ..services.user_deletion import delete_unrelated_user, deletable_certificate, cleanup_doctor_certificate

bp = Blueprint("admin", __name__)


def _patient_name(case):
    snapshot = case.patient_snapshot or {}
    return (snapshot.get("full_name") if isinstance(snapshot, dict) else None) or (
        case.patient.full_name if case.patient else "Chưa có thông tin"
    )


def _case_summary(case):
    return {
        "id": case.id, "code": case.case_code,
        "patient": _patient_name(case),
        "doctor": case.doctor.full_name if case.doctor else "Chưa phân công",
        "doctor_id": case.doctor_id, "status": case.status,
        "created_at": case.created_at.isoformat() if case.created_at else None,
        "lesion_location": case.lesion_location,
    }


@bp.get("/api/admin/cases")
@require_roles("ADMIN")
def admin_cases():
    search = request.args.get("search", "").strip()[:150]
    status = request.args.get("status", "").strip().upper()
    doctor = request.args.get("doctor", "").strip()
    start = request.args.get("start", "").strip()
    end = request.args.get("end", "").strip()
    try:
        page = max(1, int(request.args.get("page", "1")))
        date_start = date.fromisoformat(start) if start else None
        date_end = date.fromisoformat(end) if end else None
    except ValueError:
        abort(400, description="Bộ lọc ngày hoặc trang không hợp lệ.")
    if date_start and date_end and date_start > date_end:
        abort(400, description="Ngày bắt đầu phải trước hoặc bằng ngày kết thúc.")
    if status and status not in {"CREATED", "UPLOADED", "ANALYZED", "REVIEWED", "COMPLETED"}:
        abort(400, description="Trạng thái ca khám không hợp lệ.")
    if doctor and not doctor.isdecimal():
        abort(400, description="Bác sĩ không hợp lệ.")
    query = db.select(Case).join(User, Case.doctor_id == User.id)
    if search:
        pattern = f"%{search}%"
        # Account-backed patient names need their own alias to avoid joining users twice.
        from sqlalchemy.orm import aliased
        patient_user = aliased(User)
        query = db.select(Case).join(User, Case.doctor_id == User.id).outerjoin(
            patient_user, Case.patient_user_id == patient_user.id
        ).where(or_(Case.case_code.ilike(pattern), User.full_name.ilike(pattern),
                    patient_user.full_name.ilike(pattern),
                    Case.patient_snapshot["full_name"].as_string().ilike(pattern)))
    if status:
        query = query.where(Case.status == status)
    if doctor:
        query = query.where(Case.doctor_id == int(doctor))
    if date_start:
        query = query.where(Case.created_at >= datetime.combine(date_start, datetime.min.time()))
    if date_end:
        query = query.where(Case.created_at < datetime.combine(date_end + timedelta(days=1), datetime.min.time()))
    total = db.session.scalar(db.select(func.count()).select_from(query.order_by(None).subquery())) or 0
    page_size = 15
    items = db.session.scalars(query.options(selectinload(Case.patient), selectinload(Case.doctor))
                               .order_by(Case.created_at.desc(), Case.id.desc())
                               .offset((page - 1) * page_size).limit(page_size)).all()
    counts = dict(db.session.execute(db.select(Case.status, func.count(Case.id)).group_by(Case.status)).all())
    doctors = db.session.scalars(db.select(User).where(User.role == "DOCTOR").order_by(User.full_name)).all()
    return jsonify(cases=[_case_summary(item) for item in items], page=page,
                   pages=max(1, (total + page_size - 1) // page_size), total=total,
                   metrics={"total": sum(counts.values()), "processing": sum(counts.get(key, 0) for key in ("CREATED", "UPLOADED", "ANALYZED", "REVIEWED")), "completed": counts.get("COMPLETED", 0)},
                   doctors=[{"id": item.id, "name": item.full_name} for item in doctors])


@bp.get("/api/admin/cases/<int:case_id>")
@require_roles("ADMIN")
def admin_case_detail(case_id):
    case = db.session.get(Case, case_id)
    if not case:
        abort(404)
    data = _case_summary(case)
    data["images"] = [{"id": item.id, "filename": item.original_filename,
                        "status": item.status,
                        "url": f"/api/admin/cases/{case.id}/images/{item.id}/original"}
                       for item in case.images]
    data["analyses"] = [{
        "id": item.id, "image_id": item.case_image_id, "status": item.status,
        "area": item.lesion_area_px, "perimeter": item.lesion_perimeter_px,
        "ratio": item.lesion_ratio,
        "gradcam_url": f"/api/admin/cases/{case.id}/images/{item.id}/gradcam" if item.gradcam_path else None,
        "contour_url": f"/api/admin/cases/{case.id}/images/{item.id}/contour" if item.contour_path else None,
        "results": [{"model": result.model_name, "class": result.predicted_class,
                     "probability": result.predicted_probability, "binary": result.binary_result,
                     "class_probabilities": result.class_probabilities}
                    for result in item.results],
    } for item in case.analyses]
    data["reviews"] = [{"status": item.review_status, "doctor": item.doctor.full_name if item.doctor else "-",
                        "note": item.clinical_note, "conclusion": item.doctor_conclusion,
                        "recommendation": item.recommendation} for item in case.reviews]
    return jsonify(data)


@bp.get("/api/admin/cases/<int:case_id>/images/<int:image_id>/<kind>")
@require_roles("ADMIN")
def admin_case_image(case_id, image_id, kind):
    case = db.session.get(Case, case_id)
    if case is None:
        abort(404)
    if kind == "original":
        image = db.session.get(CaseImage, image_id)
        if not image or image.case_id != case_id:
            abort(404)
        path = image.image_path
        root = Path(current_app.config["UPLOAD_FOLDER"]).resolve()
    elif kind in {"gradcam", "contour"}:
        analysis = db.session.get(Analysis, image_id)
        if not analysis or analysis.case_id != case_id:
            abort(404)
        path = analysis.gradcam_path if kind == "gradcam" else analysis.contour_path
        root = (Path(current_app.config["PROJECT_ROOT"]) / "instance" / "gradcam").resolve() if kind == "gradcam" else Path(current_app.config["MEASUREMENT_FOLDER"]).resolve()
    else:
        abort(404)
    if not path:
        abort(404)
    candidate = Path(path).resolve()
    if root not in candidate.parents or not candidate.is_file():
        abort(404)
    return send_file(candidate, as_attachment=False)


@bp.get("/api/admin/doctor-certificates/<path:filename>")
@require_roles("ADMIN")
def doctor_certificate(filename):
    root = (Path(current_app.config["UPLOAD_FOLDER"]) / "doctor-certificates").resolve()
    safe_path = (root / secure_filename(filename)).resolve()
    if root not in safe_path.parents or not safe_path.is_file():
        abort(404)
    return send_from_directory(root, safe_path.name, as_attachment=True)


@bp.post("/api/admin/doctor-applications/<int:application_id>/certificate")
@require_roles("ADMIN")
def upload_doctor_certificate(application_id):
    application = db.session.get(DoctorApplication, application_id)
    if application is None:
        abort(404)
    uploaded = request.files.get("certificate")
    if not uploaded or not uploaded.filename:
        abort(400, description="Vui lòng chọn file chứng chỉ.")
    suffix = Path(secure_filename(uploaded.filename)).suffix.lower()
    if suffix not in {".pdf", ".jpg", ".jpeg", ".png"}:
        abort(400, description="Chỉ nhận chứng chỉ PDF, JPG hoặc PNG.")
    data = uploaded.stream.read(5 * 1024 * 1024 + 1)
    if len(data) > 5 * 1024 * 1024:
        abort(413, description="File chứng chỉ tối đa 5 MB.")
    if suffix == ".pdf" and not data.startswith(b"%PDF-"):
        abort(400, description="Nội dung file PDF không hợp lệ.")
    if suffix in {".jpg", ".jpeg"} and not data.startswith(b"\xff\xd8\xff"):
        abort(400, description="Nội dung file JPG không hợp lệ.")
    if suffix == ".png" and not data.startswith(b"\x89PNG\r\n\x1a\n"):
        abort(400, description="Nội dung file PNG không hợp lệ.")
    root = Path(current_app.config["UPLOAD_FOLDER"]) / "doctor-certificates"
    root.mkdir(parents=True, exist_ok=True)
    filename = f"{application.id}-{uuid4().hex}{suffix}"
    (root / filename).write_bytes(data)
    application.certificate_path = filename
    _admin_audit("DOCTOR_CERTIFICATE_UPLOADED", application.user)
    db.session.commit()
    return jsonify(success=True, filename=filename)


def _admin_audit(event, target, success=True):
    db.session.add(AuditLog(
        user_id=current_user.id,
        email=current_user.email,
        event=event,
        success=success,
        ip_address=request.remote_addr,
        user_agent=request.headers.get("User-Agent", "")[:500],
    ))


@bp.get("/admin")
@require_roles("ADMIN")
def portal():
    return render_template("admin.html", admin=current_user)


@bp.get("/api/admin/overview")
@require_roles("ADMIN")
def overview():
    counts = {
        "users": db.session.scalar(db.select(func.count(User.id))) or 0,
        "cases": db.session.scalar(db.select(func.count(Case.id))) or 0,
        "analyses": db.session.scalar(db.select(func.count(Analysis.id))) or 0,
        "doctors": db.session.scalar(
            db.select(func.count(User.id)).where(User.role == "DOCTOR")
        ) or 0,
    }
    recent_cases = db.session.scalars(
        db.select(Case).order_by(Case.created_at.desc()).limit(6)
    ).all()
    recent_analyses = db.session.scalars(
        db.select(Analysis).order_by(Analysis.created_at.desc()).limit(6)
    ).all()
    class_labels = {
        "MEL": ("Melanoma", "Nghi ngờ ác tính", "warning"),
        "NV": ("Nevus", "Nốt ruồi lành tính", "benign"),
        "BCC": ("Basal cell carcinoma", "Ung thư tế bào đáy", "warning"),
        "AK": ("Actinic keratosis", "Dày sừng ánh sáng", "warning"),
        "AKIEC": ("Actinic keratosis", "Dày sừng ánh sáng", "warning"),
        "BKL": ("Benign keratosis", "Sừng hóa lành tính", "benign"),
        "DF": ("Dermatofibroma", "U xơ da lành tính", "benign"),
        "VASC": ("Vascular lesion", "Tổn thương mạch máu", "benign"),
        "SCC": ("Squamous cell carcinoma", "Ung thư tế bào vảy", "warning"),
    }
    class_counts = {key: 0 for key in ("MEL", "NV", "BCC", "AKIEC", "BKL", "DF", "VASC", "SCC")}
    grouped_results = db.session.execute(
        db.select(
            func.upper(AnalysisResult.predicted_class),
            func.count(AnalysisResult.id),
        )
        .where(AnalysisResult.predicted_class.is_not(None))
        .group_by(func.upper(AnalysisResult.predicted_class))
    )
    for predicted_class, count in grouped_results:
        if predicted_class in class_counts:
            class_counts[predicted_class] += count
        elif predicted_class == "AK":
            class_counts["AKIEC"] += count
    total_results = sum(class_counts.values())
    analysis_distribution = [
        {
            "key": key,
            "name": class_labels[key][0],
            "label": class_labels[key][1],
            "type": class_labels[key][2],
            "count": count,
            "percentage": round(count / total_results * 100, 1) if total_results else 0,
        }
        for key, count in class_counts.items()
    ]
    month_keys = []
    cursor = date.today().replace(day=1)
    for _ in range(6):
        month_keys.append(cursor.strftime("%Y-%m"))
        cursor = (
            cursor.replace(day=1) - date.resolution
        ).replace(day=1)
    month_keys.reverse()
    case_by_month = dict(
        db.session.execute(
            db.select(
                func.strftime("%Y-%m", Case.created_at),
                func.count(Case.id),
            )
            .where(func.strftime("%Y-%m", Case.created_at).in_(month_keys))
            .group_by(func.strftime("%Y-%m", Case.created_at))
        ).all()
    )
    analysis_by_month = dict(
        db.session.execute(
            db.select(
                func.strftime("%Y-%m", Analysis.created_at),
                func.count(Analysis.id),
            )
            .where(func.strftime("%Y-%m", Analysis.created_at).in_(month_keys))
            .group_by(func.strftime("%Y-%m", Analysis.created_at))
        ).all()
    )
    trends = [
        {
            "key": month_key,
            "label": f"Thg {int(month_key[5:])}",
            "cases": case_by_month.get(month_key, 0),
            "analyses": analysis_by_month.get(month_key, 0),
        }
        for month_key in month_keys
    ]
    return jsonify(
        counts=counts,
        trends=trends,
        recent_cases=[
            {
                "code": case.case_code,
                "status": case.status,
                "doctor": case.doctor.full_name if case.doctor else "Chưa phân công",
                "created_at": case.created_at.strftime("%d/%m/%Y"),
            }
            for case in recent_cases
        ],
        recent_analyses=[
            {
                "id": analysis.id,
                "status": analysis.status,
                "model": (
                    analysis.results[0].model_name
                    if analysis.results
                    else "EfficientNet-B0"
                ),
                "prediction": (
                    analysis.results[0].predicted_class
                    if analysis.results and analysis.results[0].predicted_class
                    else "Đang xử lý",
            ),
            }
            for analysis in recent_analyses
        ],
        analysis_distribution=analysis_distribution,
    )


@bp.get("/api/admin/users")
@require_roles("ADMIN")
def users():
    search = request.args.get("search", "").strip()
    role = request.args.get("role", "").strip().upper()
    status = request.args.get("status", "").strip().upper()
    query = db.select(User).where(User.deleted_at.is_(None)).order_by(User.created_at.desc())
    if search:
        term = f"%{search}%"
        query = query.where(or_(User.full_name.ilike(term), User.email.ilike(term)))
    if role in {"ADMIN", "DOCTOR", "USER"}:
        query = query.where(User.role == role)
    if status == "ACTIVE":
        query = query.where(User.is_active.is_(True))
    elif status == "LOCKED":
        query = query.where(User.is_active.is_(False))
    records = db.session.scalars(query.limit(100)).all()
    return jsonify(
        users=[
            {
                "id": user.id,
                "name": user.full_name,
                "email": user.email,
                "role": user.role,
                "active": user.is_active,
                "deleted": user.deleted_at is not None,
                "created_at": user.created_at.strftime("%d/%m/%Y"),
            }
            for user in records
        ]
    )


@bp.post("/api/admin/users")
@require_roles("ADMIN")
def create_user():
    payload = request.get_json(silent=True) or {}
    name = payload.get("name", "").strip()
    email = payload.get("email", "").strip().lower()
    password = payload.get("password", "")
    role = payload.get("role", "USER").upper()
    if not (2 <= len(name) <= 150) or "@" not in email:
        abort(400, description="Họ tên hoặc email không hợp lệ.")
    if role not in {"ADMIN", "DOCTOR", "USER"}:
        abort(400, description="Vai trò không hợp lệ.")
    if not isinstance(password, str) or not 12 <= len(password) <= 256:
        abort(400, description="Mật khẩu phải có từ 12 đến 256 ký tự.")
    if db.session.scalar(db.select(User).where(User.email == email)):
        return jsonify(success=False, message="Email đã được sử dụng."), 409
    user = User(email=email, full_name=name, role=role)
    user.set_password(password)
    db.session.add(user)
    _admin_audit("USER_CREATED", user)
    db.session.commit()
    return jsonify(success=True), 201


@bp.patch("/api/admin/users/<int:user_id>/status")
@require_roles("ADMIN")
def update_user_status(user_id):
    user = db.session.get(User, user_id)
    if user is None:
        abort(404)
    if user.id == current_user.id:
        return jsonify(success=False, message="Không thể khóa tài khoản đang đăng nhập."), 400
    if not user.is_active and user.role == "DOCTOR":
        approved = db.session.scalar(
            db.select(DoctorApplication.id).where(
                DoctorApplication.user_id == user.id,
                DoctorApplication.status == "APPROVED",
            )
        )
        if approved is None:
            return jsonify(
                success=False,
                message="Không thể mở khóa bác sĩ chưa được phê duyệt. Vui lòng xét duyệt hồ sơ tại Quản lý Bác sĩ & Duyệt trước.",
            ), 409
    user.is_active = not user.is_active
    _admin_audit("USER_UNLOCK" if user.is_active else "USER_LOCK", user)
    db.session.commit()
    return jsonify(success=True, active=user.is_active)


@bp.patch("/api/admin/users/<int:user_id>/role")
@require_roles("ADMIN")
def update_user_role(user_id):
    user = db.session.get(User, user_id)
    payload = request.get_json(silent=True) or {}
    role = str(payload.get("role", "")).upper()
    if user is None:
        abort(404)
    if role not in {"ADMIN", "DOCTOR", "USER"}:
        abort(400, description="Vai trò không hợp lệ.")
    if user.id == current_user.id and role != "ADMIN":
        return jsonify(success=False, message="Không thể hạ quyền tài khoản đang đăng nhập."), 400
    user.role = role
    _admin_audit("USER_ROLE_CHANGED", user)
    db.session.commit()
    return jsonify(success=True, role=user.role)


@bp.delete("/api/admin/users/<int:user_id>")
@require_roles("ADMIN")
def delete_user_permanently(user_id):
    user = db.session.get(User, user_id)
    if user is None:
        abort(404)
    if user.id == current_user.id:
        return jsonify(success=False, message="Không thể xóa tài khoản đang đăng nhập."), 400
    certificate = deletable_certificate(user)
    blocker = delete_unrelated_user(user)
    if blocker:
        return jsonify(success=False, message=blocker), 409
    _admin_audit("USER_PERMANENTLY_DELETED", None)
    db.session.commit()
    cleanup_doctor_certificate(certificate)
    return jsonify(success=True, message="Đã xóa vĩnh viễn tài khoản. Email có thể đăng ký lại.")


@bp.get("/api/admin/doctor-applications")
@require_roles("ADMIN")
def doctor_applications():
    applications = db.session.scalars(
        db.select(DoctorApplication)
        .where(DoctorApplication.status == "PENDING")
        .order_by(DoctorApplication.created_at.asc())
    ).all()
    return jsonify(applications=[{
        "id": item.id,
        "user_id": item.user_id,
        "name": item.user.full_name,
        "email": item.user.email,
        "certificate_path": item.certificate_path,
        "created_at": item.created_at.isoformat(),
    } for item in applications])


@bp.get("/api/admin/doctor-applications/history")
@require_roles("ADMIN")
def doctor_application_history():
    status = request.args.get("status", "").strip().upper()
    if status not in {"", "APPROVED", "REJECTED"}:
        return jsonify(success=False, message="Trạng thái xét duyệt không hợp lệ."), 400
    query = db.select(DoctorApplication).where(DoctorApplication.status.in_(("APPROVED", "REJECTED")))
    if status:
        query = query.where(DoctorApplication.status == status)
    search = request.args.get("search", "").strip()
    if search:
        term = f"%{search}%"
        query = query.join(DoctorApplication.user).where(or_(User.full_name.ilike(term), User.email.ilike(term)))
    try:
        start = request.args.get("from", "").strip()
        end = request.args.get("to", "").strip()
        if start:
            query = query.where(DoctorApplication.reviewed_at >= datetime.strptime(start, "%Y-%m-%d"))
        if end:
            query = query.where(DoctorApplication.reviewed_at < datetime.strptime(end, "%Y-%m-%d") + timedelta(days=1))
    except ValueError:
        return jsonify(success=False, message="Ngày lọc không hợp lệ."), 400
    applications = db.session.scalars(query.options(
        selectinload(DoctorApplication.user), selectinload(DoctorApplication.reviewer)
    ).order_by(DoctorApplication.reviewed_at.desc(), DoctorApplication.id.desc())).all()
    return jsonify(applications=[{
        "id": item.id, "user_id": item.user_id, "name": item.user.full_name,
        "email": item.user.email, "certificate_path": item.certificate_path,
        "status": item.status, "reviewed_at": item.reviewed_at.isoformat() if item.reviewed_at else None,
        "reviewer_name": item.reviewer.full_name if item.reviewer else "Không xác định",
        "rejection_reason": item.rejection_reason,
        "email_status": item.email_notification_status,
    } for item in applications])


@bp.patch("/api/admin/doctor-applications/<int:application_id>")
@require_roles("ADMIN")
def review_doctor_application(application_id):
    application = db.session.get(DoctorApplication, application_id)
    payload = request.get_json(silent=True) or {}
    decision = str(payload.get("decision", "")).upper()
    if application is None or application.status != "PENDING":
        abort(404)
    if decision not in {"APPROVE", "REJECT"}:
        abort(400, description="Quyết định duyệt không hợp lệ.")
    reason = str(payload.get("reason") or "").strip()
    if decision == "REJECT" and (not reason or len(reason) > 1000):
        return jsonify(success=False, message="Vui lòng nhập lý do từ chối (tối đa 1000 ký tự)."), 400
    if decision == "APPROVE" and not application.certificate_path:
        return jsonify(success=False, message="Cần tải chứng chỉ trước khi phê duyệt."), 400
    application.status = "APPROVED" if decision == "APPROVE" else "REJECTED"
    application.rejection_reason = reason if decision == "REJECT" else None
    application.reviewed_by = current_user.id
    application.reviewed_at = utcnow()
    application.user.is_active = decision == "APPROVE"
    _admin_audit("DOCTOR_APPLICATION_" + decision, application.user)
    db.session.commit()
    notification = (_send_doctor_approval_email(application.user) if decision == "APPROVE"
                    else _send_doctor_rejection_email(application.user, reason))
    application.email_notification_status = "SENT" if notification["sent"] else "FAILED"
    db.session.commit()
    return jsonify(success=True, status=application.status, email_notification=notification)


def _send_doctor_approval_email(doctor):
    """Notify after committing approval; SMTP failures never undo activation."""
    warning = "Tài khoản bác sĩ đã được phê duyệt nhưng chưa gửi được email thông báo."
    try:
        if not all(current_app.config.get(key) for key in (
            "MAIL_SERVER", "MAIL_USERNAME", "MAIL_PASSWORD", "MAIL_DEFAULT_SENDER"
        )):
            raise RuntimeError("SMTP chưa được cấu hình đầy đủ")
        mail.send(Message(
            subject="[DermaScan AI] Tài khoản bác sĩ đã được phê duyệt",
            recipients=[doctor.email],
            html=render_template('emails/doctor_approved.html', DOCTOR_NAME=doctor.full_name, LOGIN_URL=request.url_root),
            body=(
                f"Kính gửi Bác sĩ {doctor.full_name},\n\n"
                "Tài khoản bác sĩ của bạn trên hệ thống DermaScan AI đã được "
                "quản trị viên phê duyệt thành công và hiện đã được kích hoạt.\n\n"
                "Bạn có thể đăng nhập bằng email và mật khẩu đã đăng ký. "
                "Hệ thống sẽ gửi mã OTP qua email mỗi khi bạn đăng nhập.\n\n"
                "Trân trọng,\nĐội ngũ DermaScan AI"
            ),
        ))
    except Exception:
        current_app.logger.exception("Không thể gửi email phê duyệt cho bác sĩ id=%s", doctor.id)
        return {"sent": False, "message": warning}
    return {"sent": True, "message": "Đã gửi email thông báo phê duyệt cho bác sĩ."}


def _send_doctor_rejection_email(doctor, reason):
    """Send rejection after commit so SMTP failures never reverse the decision."""
    try:
        if not all(current_app.config.get(key) for key in (
            "MAIL_SERVER", "MAIL_USERNAME", "MAIL_PASSWORD", "MAIL_DEFAULT_SENDER"
        )):
            raise RuntimeError("SMTP chưa được cấu hình đầy đủ")
        mail.send(Message(
            subject="[DermaScan AI] Thông báo kết quả xét duyệt hồ sơ bác sĩ",
            recipients=[doctor.email],
            html=render_template('emails/doctor_rejected.html', DOCTOR_NAME=doctor.full_name, REJECTION_REASON=reason, SUPPORT_URL='mailto:' + (current_app.config.get('SUPPORT_EMAIL') or current_app.config['MAIL_DEFAULT_SENDER'])),
            body=(
                f"Kính gửi Bác sĩ {doctor.full_name},\n\n"
                "Hồ sơ đăng ký bác sĩ của bạn trên DermaScan AI chưa được chấp thuận.\n"
                f"Lý do: {reason}\n\n"
                "Trân trọng,\nĐội ngũ DermaScan AI"
            ),
        ))
    except Exception:
        current_app.logger.exception("Không thể gửi email từ chối hồ sơ bác sĩ id=%s", doctor.id)
        return {"sent": False, "message": "Đã từ chối hồ sơ nhưng không gửi được email thông báo."}
    return {"sent": True, "message": "Đã gửi email thông báo từ chối cho bác sĩ."}


@bp.get("/api/admin/audit-logs")
@require_roles("ADMIN")
def audit_logs():
    try:
        page = max(1, int(request.args.get("page", 1)))
        per_page = min(100, max(1, int(request.args.get("per_page", 25))))
    except ValueError:
        abort(400, description="Trang audit log không hợp lệ.")
    query = db.select(AuditLog)
    actor_email = request.args.get("actor", "").strip()
    if actor_email:
        query = query.where(AuditLog.email.ilike(f"%{actor_email}%"))
    search = request.args.get("search", "").strip()
    if search:
        query = query.where(or_(AuditLog.email.ilike(f"%{search}%"), AuditLog.event.ilike(f"%{search}%")))
    event = request.args.get("event", "").strip().upper()
    if event:
        query = query.where(AuditLog.event == event)
    start = request.args.get("start", "").strip()
    end = request.args.get("end", "").strip()
    try:
        if start:
            query = query.where(AuditLog.created_at >= datetime.fromisoformat(start))
        if end:
            query = query.where(AuditLog.created_at < datetime.fromisoformat(end) + timedelta(days=1))
    except ValueError:
        abort(400, description="Khoảng ngày audit log không hợp lệ.")
    total = db.session.scalar(db.select(func.count()).select_from(query.subquery())) or 0
    records = db.session.scalars(query.order_by(AuditLog.created_at.desc()).offset((page - 1) * per_page).limit(per_page)).all()
    return jsonify(logs=[{
        "id": item.id, "email": item.email, "event": item.event,
        "ip_address": item.ip_address, "user_agent": item.user_agent,
        "success": item.success, "created_at": item.created_at.isoformat(),
    } for item in records], page=page, per_page=per_page, total=total,
        pages=max(1, (total + per_page - 1) // per_page))


@bp.get("/api/admin/audit-logs.csv")
@require_roles("ADMIN")
def export_audit_logs():
    query = db.select(AuditLog)
    start = request.args.get("start", "").strip()
    end = request.args.get("end", "").strip()
    try:
        if start:
            query = query.where(AuditLog.created_at >= datetime.fromisoformat(start))
        if end:
            query = query.where(AuditLog.created_at < datetime.fromisoformat(end) + timedelta(days=1))
    except ValueError:
        abort(400, description="Kho?ng ng?y audit log kh?ng h?p l?.")
    records = db.session.scalars(query.order_by(AuditLog.created_at.desc()).limit(10000)).all()
    def csv_cell(value):
        return '"' + str(value or "").replace('"', '""') + '"'
    rows = ["created_at,email,event,ip_address,success"]
    rows.extend(",".join(csv_cell(value) for value in (
        item.created_at.isoformat(), item.email, item.event, item.ip_address,
        "true" if item.success else "false",
    )) for item in records)
    from flask import Response
    return Response("\ufeff" + "\r\n".join(rows), mimetype="text/csv",
                    headers={"Content-Disposition": "attachment; filename=audit-log.csv"})


@bp.get("/api/admin/security-settings")
@require_roles("ADMIN")
def get_security_settings():
    setting = db.session.get(SecuritySetting, 1) or SecuritySetting(id=1)
    if setting.id is None:
        db.session.add(setting)
        db.session.commit()
    return jsonify(
        session_timeout_minutes=setting.session_timeout_minutes,
        password_min_length=setting.password_min_length,
        require_admin_2fa=setting.require_admin_2fa,
    )


@bp.put("/api/admin/security-settings")
@require_roles("ADMIN")
def update_security_settings():
    payload = request.get_json(silent=True) or {}
    setting = db.session.get(SecuritySetting, 1)
    if setting is None:
        setting = SecuritySetting(id=1)
        db.session.add(setting)
    try:
        timeout = int(payload.get("session_timeout_minutes", setting.session_timeout_minutes))
        minimum = int(payload.get("password_min_length", setting.password_min_length))
    except (TypeError, ValueError):
        abort(400, description="Cấu hình bảo mật không hợp lệ.")
    if timeout < 5 or timeout > 1440 or minimum < 8 or minimum > 128:
        abort(400, description="Cấu hình bảo mật nằm ngoài giới hạn cho phép.")
    setting.session_timeout_minutes = timeout
    setting.password_min_length = minimum
    setting.require_admin_2fa = bool(payload.get("require_admin_2fa", setting.require_admin_2fa))
    if setting.require_admin_2fa:
        active_admins = db.session.scalars(db.select(User).where(User.role == "ADMIN", User.deleted_at.is_(None), User.is_active.is_(True))).all()
        for admin_user in active_admins:
            admin_user.two_factor_enabled = True
    _admin_audit("SECURITY_SETTINGS_UPDATED", current_user)
    db.session.commit()
    return jsonify(success=True)