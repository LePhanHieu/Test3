"""Central role + ownership rules. Routes must never query private IDs unscoped."""
from functools import wraps
from uuid import uuid4
from flask import abort
from flask_login import current_user
from ..extensions import db
from ..models import Case, User


def require_roles(*roles):
    def decorate(fn):
        @wraps(fn)
        def wrapped(*args, **kwargs):
            if not current_user.is_authenticated or not current_user.is_active:
                abort(401)
            if roles and current_user.role not in roles:
                abort(403)
            return fn(*args, **kwargs)
        return wrapped
    return decorate


def visible_cases(actor):
    query = db.select(Case)
    if actor.role == 'USER':
        return query.where(Case.patient_user_id == actor.id)
    if actor.role == 'DOCTOR':
        return query.where(Case.doctor_id == actor.id)
    if actor.role == 'ADMIN':
        return query
    abort(403)


def visible_case_or_404(case_id):
    case = db.session.scalar(visible_cases(current_user).where(Case.id == case_id))
    if case is None:
        abort(404)
    return case


def create_case(actor, patient_user_id, doctor_id=None, lesion_location=None):
    if not actor.is_active or actor.role not in ('ADMIN', 'DOCTOR'):
        abort(403)
    if actor.role == 'DOCTOR':
        if doctor_id is not None and doctor_id != actor.id:
            abort(403)
        doctor_id = actor.id
    patient = db.session.get(User, patient_user_id)
    doctor = db.session.get(User, doctor_id) if doctor_id is not None else None
    if not patient or patient.role != 'USER' or not patient.is_active:
        abort(400, description='Bệnh nhân phải là tài khoản USER đang hoạt động')
    if not doctor or doctor.role != 'DOCTOR' or not doctor.is_active:
        abort(400, description='Cần bác sĩ phụ trách hợp lệ')
    case = Case(case_code='CASE-' + uuid4().hex.upper(), patient=patient,
                doctor=doctor, lesion_location=lesion_location)
    db.session.add(case)
    db.session.commit()
    return case
