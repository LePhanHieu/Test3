from .base import Timestamps
from ..extensions import db


class AuditLog(Timestamps, db.Model):
    __tablename__ = "audit_logs"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id", ondelete="SET NULL"))
    email = db.Column(db.String(254), nullable=False)
    event = db.Column(db.String(80), nullable=False)
    ip_address = db.Column(db.String(64))
    user_agent = db.Column(db.String(500))
    success = db.Column(db.Boolean, nullable=False, default=True, server_default=db.true())
    user = db.relationship("User", backref="audit_logs")


class SecuritySetting(Timestamps, db.Model):
    __tablename__ = "security_settings"

    id = db.Column(db.Integer, primary_key=True)
    session_timeout_minutes = db.Column(db.Integer, nullable=False, default=30, server_default="30")
    password_min_length = db.Column(db.Integer, nullable=False, default=12, server_default="12")
    require_admin_2fa = db.Column(db.Boolean, nullable=False, default=True, server_default=db.true())


class DoctorApplication(Timestamps, db.Model):
    __tablename__ = "doctor_applications"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id", ondelete="CASCADE"), nullable=False, unique=True)
    certificate_path = db.Column(db.String(500))
    status = db.Column(db.String(20), nullable=False, default="PENDING", server_default="PENDING")
    reviewed_by = db.Column(db.Integer, db.ForeignKey("users.id", ondelete="SET NULL"))
    reviewed_at = db.Column(db.DateTime)
    rejection_reason = db.Column(db.Text)
    email_notification_status = db.Column(db.String(20))
    user = db.relationship("User", foreign_keys=[user_id], backref="doctor_application", uselist=False)
    reviewer = db.relationship("User", foreign_keys=[reviewed_by])