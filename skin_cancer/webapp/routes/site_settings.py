from flask import Blueprint, abort, current_app, jsonify, request, send_file
from flask_login import current_user

from ..extensions import db
from ..models import SiteSetting
from ..models import Slide
from ..services.access import require_roles
from ..services.site_settings_service import SiteSettingsService, SiteSettingsValidationError
from ..services.site_media_service import SiteMediaService, SiteMediaError
from ..services.slide_service import SlideService, SlideValidationError, SlideImageError


bp = Blueprint('site_settings', __name__)


def _payload():
    payload = request.get_json(silent=True)
    return payload if isinstance(payload, dict) else None


def _validation_response(error):
    return jsonify(success=False, message=str(error)), 400


@bp.get('/api/site-settings')
def public_site_settings():
    return jsonify(SiteSettingsService(current_app).serialize())


@bp.put('/api/admin/site-settings')
@require_roles('ADMIN')
def admin_update_site_settings():
    payload = _payload()
    if payload is None:
        return _validation_response('Payload site settings không hợp lệ.')

    # The singleton identity is server-owned; a client-provided id is ignored.
    payload = dict(payload)
    payload.pop('id', None)
    service = SiteSettingsService(current_app)
    try:
        data = service.validate_payload(payload)
    except SiteSettingsValidationError as error:
        return _validation_response(error)

    setting = service.get_record()
    if setting is None:
        setting = SiteSetting(id=1, **service.FALLBACKS)
        db.session.add(setting)
    for name, value in data.items():
        setattr(setting, name, value)
    setting.updated_by = current_user.id
    db.session.commit()
    return jsonify(service.serialize(setting, include_admin=True))


@bp.post('/api/admin/homepage/save')
@require_roles('ADMIN')
def admin_save_homepage():
    """Apply site settings and slideshow edits within one database transaction."""
    payload = _payload()
    if payload is None or not isinstance(payload.get('settings'), dict) or not isinstance(payload.get('slides'), list):
        return _validation_response('Nội dung trang chủ không hợp lệ.')
    slides_data = payload['slides']
    if len(slides_data) > 20:
        return _validation_response('Tối đa 20 banner.')
    service = SiteSettingsService(current_app)
    slide_service = SlideService(current_app)
    try:
        settings_data = service.validate_payload(payload['settings'])
        prepared_slides = []
        existing_slides = {slide.id: slide for slide in db.session.scalars(db.select(Slide)).all()}
        submitted_ids = []
        for position, raw in enumerate(slides_data):
            if not isinstance(raw, dict):
                raise SlideValidationError('Dữ liệu banner không hợp lệ.')
            slide_id = raw.get('id')
            if slide_id is not None and (type(slide_id) is not int or slide_id not in existing_slides):
                raise SlideValidationError('Banner không tồn tại.')
            if slide_id is not None:
                submitted_ids.append(slide_id)
            fields = {k: v for k, v in raw.items() if k != 'id'}
            fields['display_order'] = position
            clean = slide_service.validate_payload(fields)
            # Image references may use bundled assets or validated site-media files.
            slide_service.resolve_image_path(Slide(image_path=clean['image_path']))
            prepared_slides.append((slide_id, clean))
        if len(submitted_ids) != len(set(submitted_ids)):
            raise SlideValidationError('Một banner xuất hiện nhiều lần.')
        # Validate changed logo/favicon against actual files before saving.
        for field in ('logo_path', 'favicon_path'):
            if field in settings_data and settings_data[field]:
                service.resolve_asset_path(settings_data[field])
    except (SiteSettingsValidationError, SlideValidationError, SlideImageError) as error:
        return _validation_response(error)

    try:
        setting = service.get_record()
        if setting is None:
            setting = SiteSetting(id=1, **service.FALLBACKS)
            db.session.add(setting)
        for field, value in settings_data.items():
            setattr(setting, field, value)
        setting.updated_by = current_user.id
        for slide_id, data in prepared_slides:
            if slide_id is None:
                db.session.add(Slide(created_by=current_user.id, **data))
            else:
                slide = existing_slides[slide_id]
                for field, value in data.items():
                    setattr(slide, field, value)
        for slide_id, slide in existing_slides.items():
            if slide_id not in submitted_ids:
                db.session.delete(slide)
        db.session.commit()
    except Exception:
        db.session.rollback()
        current_app.logger.exception('Could not save homepage settings')
        return jsonify(success=False, message='Không lưu được cấu hình trang chủ.'), 500
    return jsonify(success=True, settings=service.serialize(setting, include_admin=True),
                   slides=[slide_service.serialize(item, include_admin=True) for item in
                           db.session.scalars(db.select(Slide).order_by(Slide.display_order)).all()])


@bp.get('/api/site-settings/assets/<asset_kind>')
def site_settings_asset(asset_kind):
    field = {'logo': 'logo_path', 'favicon': 'favicon_path'}.get(asset_kind)
    if field is None:
        abort(404)
    service = SiteSettingsService(current_app)
    resolved = service.resolve()
    try:
        path = service.resolve_asset_path(resolved[field])
    except SiteSettingsValidationError:
        abort(404)
    return send_file(path, conditional=True, max_age=300)


@bp.get('/api/admin/site-media')
@require_roles('ADMIN')
def admin_site_media():
    return jsonify(images=SiteMediaService(current_app).list_images())


@bp.post('/api/admin/site-media')
@require_roles('ADMIN')
def admin_upload_site_media():
    try:
        path = SiteMediaService(current_app).upload(
            request.files.get('image'), request.form.get('kind', '')
        )
    except SiteMediaError as error:
        return _validation_response(error)
    return jsonify(success=True, path=path), 201


@bp.get('/api/admin/site-media/image')
@require_roles('ADMIN')
def admin_site_media_image():
    try:
        path = SiteMediaService(current_app).resolve(request.args.get('path'))
    except SiteMediaError:
        abort(404)
    return send_file(path, conditional=True, max_age=60)