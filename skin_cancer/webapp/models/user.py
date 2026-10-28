from flask_login import UserMixin
from werkzeug.security import generate_password_hash, check_password_hash
from sqlalchemy.orm import validates
from ..extensions import db
from .base import Timestamps


class User(UserMixin, Timestamps, db.Model):
    __tablename__ = 'users'
    __table_args__ = (db.CheckConstraint("role IN ('ADMIN','DOCTOR','USER')", name='role'),)
    id = db.Column(db.Integer, primary_key=True)
    full_name = db.Column(db.String(150), nullable=False)
    email = db.Column(db.String(254, collation='NOCASE'), nullable=False, unique=True)
    password_hash = db.Column(db.String(255), nullable=False)
    role = db.Column(db.String(10), nullable=False, default='USER', server_default='USER')
    date_of_birth = db.Column(db.Date)
    gender = db.Column(db.String(30))
    phone = db.Column(db.String(30))
    avatar_url = db.Column(db.String(500))
    is_active = db.Column(db.Boolean, nullable=False, default=True, server_default=db.true())
    deleted_at = db.Column(db.DateTime)
    email_verified = db.Column(db.Boolean, nullable=False, default=False, server_default=db.false())
    email_verification_token_hash = db.Column(db.String(64), unique=True)
    email_verification_expires_at = db.Column(db.DateTime)
    password_reset_token_hash = db.Column(db.String(64), unique=True)
    password_reset_expires_at = db.Column(db.DateTime)
    two_factor_enabled = db.Column(db.Boolean, nullable=False, default=False, server_default=db.false())
    two_factor_code_hash = db.Column(db.String(64))
    two_factor_code_expires_at = db.Column(db.DateTime)
    patient_cases = db.relationship('Case', foreign_keys='Case.patient_user_id', back_populates='patient', passive_deletes='all')
    assigned_cases = db.relationship('Case', foreign_keys='Case.doctor_id', back_populates='doctor', passive_deletes='all')

    @validates('email')
    def normalize_email(self, _key, value):
        if not isinstance(value, str) or '@' not in value or len(value.strip()) > 254:
            raise ValueError('Email không hợp lệ')
        return value.strip().lower()

    def set_password(self, password):
        if not isinstance(password, str) or len(password) < 12 or len(password) > 256:
            raise ValueError('Mật khẩu phải có 12–256 ký tự')
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        return isinstance(password, str) and check_password_hash(self.password_hash, password)
