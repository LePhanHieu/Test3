from flask import Blueprint, current_app, jsonify, request
from flask_login import current_user

from ..extensions import limiter
from ..services.access import require_roles
from ..services.email_service import (EmailService, INVALID_EMAIL, MISSING_PDF,
                                      UNSAFE_PDF)
from .reports import get_visible_report


bp = Blueprint('report_email', __name__, url_prefix='/api/reports')


@bp.post('/<int:report_id>/email')
@limiter.limit(
    lambda: current_app.config["RATELIMIT_EXPENSIVE"]
)
@require_roles('ADMIN', 'DOCTOR')
def send_report_email(report_id):
    report = get_visible_report(report_id)
    payload = request.get_json(silent=True)
    if payload is None:
        payload = {}
    if not isinstance(payload, dict):
        return jsonify(success=False, message='Payload không hợp lệ'), 400

    recipient = payload.get('recipient_email')
    subject = payload.get('subject')
    if recipient is not None and not isinstance(recipient, str):
        return jsonify(success=False, message='Email người nhận không hợp lệ'), 400
    if subject is not None and not isinstance(subject, str):
        return jsonify(success=False, message='Subject không hợp lệ'), 400

    result = EmailService(current_app).send_report(
        report, current_user, recipient_email=recipient, subject=subject)
    body = {
        'success': result.ok,
        'id': result.log.id,
        'report_id': result.log.report_id,
        'recipient_email': result.log.recipient_email,
        'subject': result.log.subject,
        'status': result.log.status,
        'sent_at': result.log.sent_at.isoformat() if result.log.sent_at else None,
        'message': result.message,
    }
    if result.ok:
        status_code = 201
    elif result.message in {INVALID_EMAIL, MISSING_PDF, UNSAFE_PDF}:
        status_code = 400
    else:
        status_code = 502
    return jsonify(body), status_code
