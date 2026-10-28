from flask import Blueprint, abort, current_app, jsonify, request, send_file
from flask_login import current_user

from ..extensions import db
from ..models import Slide
from ..services.access import require_roles
from ..services.slide_service import SlideImageError, SlideService, SlideValidationError


bp = Blueprint('slides', __name__)


def _payload():
    payload = request.get_json(silent=True)
    return payload if isinstance(payload, dict) else None


def _validation_response(error):
    return jsonify(success=False, message=str(error)), 400


def _admin_slide(slide_id):
    slide = db.session.get(Slide, slide_id)
    if slide is None:
        abort(404)
    return slide


@bp.get('/api/slides/active')
def active_slides():
    service = SlideService(current_app)
    slides = service.active_slides(now=current_app.config.get('SLIDE_NOW'))
    return jsonify(slides=[service.serialize(slide) for slide in slides])


@bp.get('/api/slides/<int:slide_id>/image')
def slide_image(slide_id):
    slide = db.session.get(Slide, slide_id)
    if slide is None:
        abort(404)
    service = SlideService(current_app)
    active_ids = {item.id for item in service.active_slides(now=current_app.config.get('SLIDE_NOW'))}
    if slide.id not in active_ids:
        abort(404)
    try:
        path = service.resolve_image_path(slide)
    except SlideImageError:
        abort(404)
    return send_file(path, conditional=True, max_age=300)


@bp.get('/api/admin/slides')
@require_roles('ADMIN')
def admin_list_slides():
    service = SlideService(current_app)
    slides = db.session.scalars(db.select(Slide).order_by(Slide.display_order.asc(), Slide.id.asc())).all()
    return jsonify(slides=[service.serialize(slide, include_admin=True) for slide in slides])


@bp.get('/api/admin/slides/<int:slide_id>')
@require_roles('ADMIN')
def admin_get_slide(slide_id):
    return jsonify(SlideService(current_app).serialize(_admin_slide(slide_id), include_admin=True))


@bp.post('/api/admin/slides')
@require_roles('ADMIN')
def admin_create_slide():
    payload = _payload()
    if payload is None:
        return _validation_response('Payload slide không hợp lệ.')
    service = SlideService(current_app)
    try:
        data = service.validate_payload(payload)
    except SlideValidationError as error:
        return _validation_response(error)
    slide = Slide(created_by=current_user.id, **data)
    db.session.add(slide)
    db.session.commit()
    return jsonify(service.serialize(slide, include_admin=True)), 201


@bp.patch('/api/admin/slides/<int:slide_id>')
@require_roles('ADMIN')
def admin_update_slide(slide_id):
    slide = _admin_slide(slide_id)
    payload = _payload()
    if payload is None:
        return _validation_response('Payload slide không hợp lệ.')
    service = SlideService(current_app)
    current = {name: getattr(slide, name) for name in service.FIELDS}
    current.update(payload)
    try:
        data = service.validate_payload(current)
    except SlideValidationError as error:
        return _validation_response(error)
    for name, value in data.items():
        setattr(slide, name, value)
    db.session.commit()
    return jsonify(service.serialize(slide, include_admin=True))


@bp.delete('/api/admin/slides/<int:slide_id>')
@require_roles('ADMIN')
def admin_delete_slide(slide_id):
    slide = _admin_slide(slide_id)
    db.session.delete(slide)
    db.session.commit()
    return jsonify(success=True, id=slide_id)


@bp.post('/api/admin/slides/<int:slide_id>/toggle')
@require_roles('ADMIN')
def admin_toggle_slide(slide_id):
    slide = _admin_slide(slide_id)
    slide.is_active = not slide.is_active
    db.session.commit()
    return jsonify(SlideService(current_app).serialize(slide, include_admin=True))


@bp.post('/api/admin/slides/reorder')
@require_roles('ADMIN')
def admin_reorder_slides():
    payload = _payload()
    ordered_ids = payload.get('ordered_ids') if payload else None
    if not isinstance(ordered_ids, list) or any(not isinstance(value, int) or isinstance(value, bool)
                                                for value in ordered_ids):
        return _validation_response('ordered_ids phải là danh sách số nguyên.')
    slides = db.session.scalars(db.select(Slide)).all()
    by_id = {slide.id: slide for slide in slides}
    if len(ordered_ids) != len(set(ordered_ids)) or set(ordered_ids) != set(by_id):
        return _validation_response('ordered_ids phải chứa đúng mỗi slide một lần.')
    for order, slide_id in enumerate(ordered_ids):
        by_id[slide_id].display_order = order
    db.session.commit()
    service = SlideService(current_app)
    ordered = sorted(slides, key=lambda slide: (slide.display_order, slide.id))
    return jsonify(slides=[service.serialize(slide, include_admin=True) for slide in ordered])
