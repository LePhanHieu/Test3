"""Database-driven slide validation, filtering and safe image resolution."""
from datetime import datetime, timezone
from pathlib import Path, PureWindowsPath
from urllib.parse import urlparse

from sqlalchemy import or_

from ..extensions import db
from ..models import Slide


class SlideValidationError(ValueError):
    pass


class SlideImageError(ValueError):
    pass


class SlideService:
    FIELDS = {
        'title', 'subtitle', 'image_path', 'button_text', 'button_url',
        'display_order', 'is_active', 'start_at', 'end_at',
    }
    IMAGE_SUFFIXES = {'.jpg', '.jpeg', '.png', '.webp', '.gif'}

    def __init__(self, app):
        self.app = app

    def active_slides(self, now=None):
        now = self._naive_utc(now or datetime.now(timezone.utc))
        query = db.select(Slide).where(
            Slide.is_active.is_(True),
            or_(Slide.start_at.is_(None), Slide.start_at <= now),
            or_(Slide.end_at.is_(None), Slide.end_at >= now),
        ).order_by(Slide.display_order.asc(), Slide.id.asc())
        return list(db.session.scalars(query))

    def serialize(self, slide, include_admin=False):
        result = {
            'id': slide.id,
            'title': slide.title,
            'subtitle': slide.subtitle,
            'image_url': f'/api/slides/{slide.id}/image',
            'image_path': slide.image_path if include_admin else None,
            'button_text': slide.button_text,
            'button_url': slide.button_url,
            'display_order': slide.display_order,
            'is_active': bool(slide.is_active),
            'start_at': slide.start_at.isoformat() if slide.start_at else None,
            'end_at': slide.end_at.isoformat() if slide.end_at else None,
        }
        if not include_admin:
            result.pop('image_path')
            result.pop('is_active')
        else:
            result.update({
                'created_by': slide.created_by,
                'created_at': slide.created_at.isoformat() if slide.created_at else None,
                'updated_at': slide.updated_at.isoformat() if slide.updated_at else None,
            })
        return result

    def validate_payload(self, payload, partial=False):
        if not isinstance(payload, dict):
            raise SlideValidationError('Payload slide không hợp lệ.')
        unknown = set(payload) - self.FIELDS
        if unknown:
            raise SlideValidationError('Payload chứa field không được phép.')

        result = {}
        if not partial or 'title' in payload:
            title = self._string(payload.get('title'), 'title', 255, required=True)
            result['title'] = title
        if not partial or 'image_path' in payload:
            image_path = self._string(payload.get('image_path'), 'image_path', 500, required=True)
            result['image_path'] = image_path
        for name, limit in (('subtitle', None), ('button_text', 100)):
            if not partial or name in payload:
                value = payload.get(name)
                result[name] = None if value is None else self._string(value, name, limit)
        if not partial or 'button_url' in payload:
            value = payload.get('button_url')
            result['button_url'] = None if value in (None, '') else self._safe_url(value)
        if not partial or 'display_order' in payload:
            value = payload.get('display_order', 0)
            if isinstance(value, bool) or not isinstance(value, int) or value < 0:
                raise SlideValidationError('display_order phải là số nguyên không âm.')
            result['display_order'] = value
        if not partial or 'is_active' in payload:
            value = payload.get('is_active', True)
            if not isinstance(value, bool):
                raise SlideValidationError('is_active phải là boolean.')
            result['is_active'] = value
        for name in ('start_at', 'end_at'):
            if not partial or name in payload:
                result[name] = self._parse_datetime(payload.get(name), name)
        start = result.get('start_at') if 'start_at' in result else None
        end = result.get('end_at') if 'end_at' in result else None
        if start and end and end < start:
            raise SlideValidationError('end_at không được trước start_at.')
        return result

    def resolve_image_path(self, slide):
        raw_value = slide.image_path or ''
        raw = Path(raw_value)
        if '..' in raw.parts or PureWindowsPath(raw_value).drive:
            raise SlideImageError('Đường dẫn ảnh slide không an toàn.')
        path = raw.resolve() if raw.is_absolute() else None
        roots = self.app.config.get('SLIDE_ALLOWED_ROOTS')
        if roots is None:
            roots = [self.app.config['PROJECT_ROOT'], self.app.instance_path]
        allowed_roots = [Path(root).resolve() for root in roots]
        if path is None:
            for root in allowed_roots:
                candidate = (root / raw).resolve()
                if candidate.is_relative_to(root) and candidate.is_file():
                    path = candidate
                    break
        if path is None or not any(path.is_relative_to(root) for root in allowed_roots):
            raise SlideImageError('Đường dẫn ảnh slide không an toàn.')
        if path.suffix.lower() not in self.IMAGE_SUFFIXES or not path.is_file():
            raise SlideImageError('File ảnh slide không tồn tại hoặc không hợp lệ.')
        return path

    @staticmethod
    def _string(value, name, limit=None, required=False):
        if not isinstance(value, str):
            raise SlideValidationError(f'{name} phải là chuỗi.')
        value = value.strip()
        if required and not value:
            raise SlideValidationError(f'{name} là bắt buộc.')
        if limit is not None and len(value) > limit:
            raise SlideValidationError(f'{name} vượt quá giới hạn ký tự.')
        return value

    @staticmethod
    def _safe_url(value):
        if not isinstance(value, str) or len(value.strip()) > 500:
            raise SlideValidationError('button_url không hợp lệ.')
        value = value.strip()
        parsed = urlparse(value)
        if parsed.scheme and parsed.scheme.lower() not in {'http', 'https'}:
            raise SlideValidationError('button_url chứa scheme không được phép.')
        if not value.startswith('/') and not parsed.netloc:
            raise SlideValidationError('button_url phải là URL http(s) hoặc đường dẫn nội bộ.')
        return value

    @staticmethod
    def _parse_datetime(value, name):
        if value in (None, ''):
            return None
        if isinstance(value, datetime):
            return SlideService._naive_utc(value)
        if not isinstance(value, str):
            raise SlideValidationError(f'{name} phải là ISO-8601 datetime.')
        try:
            return SlideService._naive_utc(datetime.fromisoformat(value.replace('Z', '+00:00')))
        except ValueError as exc:
            raise SlideValidationError(f'{name} phải là ISO-8601 datetime.') from exc

    @staticmethod
    def _naive_utc(value):
        if value.tzinfo is None:
            return value
        return value.astimezone(timezone.utc).replace(tzinfo=None)