"""Fallbacks, validation and safe asset resolution for singleton site settings."""
from pathlib import Path, PureWindowsPath
from copy import deepcopy
from urllib.parse import urlparse

from ..extensions import db
from ..models import SiteSetting


class SiteSettingsValidationError(ValueError):
    """Raised when site settings contain an invalid public value."""


class SiteSettingsService:
    FIELDS = (
        'site_name', 'logo_path', 'favicon_path', 'footer_title',
        'footer_description', 'phone', 'email', 'address',
        'facebook_url', 'copyright_text', 'homepage_config',
    )
    HOMEPAGE_DEFAULTS = {
        'vi': {
            'hero': {'primary_cta': 'Phân tích ảnh', 'secondary_cta': 'Công nghệ lõi'},
            'features': {
                'eyebrow': 'Công nghệ lõi', 'title': 'Tính năng cốt lõi của DermaScan AI',
                'lead': 'Kết hợp thị giác máy tính và y khoa để hỗ trợ sàng lọc có thể giải thích.',
                'items': [
                    {'badge': 'Mô hình học sâu', 'title': 'Mô hình EfficientNet-B0', 'description': 'Phân loại tổn thương da từ ảnh dermoscopy.'},
                    {'badge': 'Giải thích kết quả', 'title': 'Trực quan hóa Grad-CAM', 'description': 'Hiển thị vùng ảnh mô hình chú ý.'},
                    {'badge': 'Dữ liệu chuẩn quốc tế', 'title': 'Bộ dữ liệu chuẩn ISIC', 'description': 'Bộ ảnh tổn thương da được chuyên gia chú giải.'},
                ],
            },
            'footer_extra': {
                'about': 'Ứng dụng y tế hỗ trợ bác sĩ sàng lọc tổn thương da bằng AI, kết hợp EfficientNet-B0 và Grad-CAM.',
                'technology': ['EfficientNet-B0 — phân loại tổn thương da', 'Grad-CAM — bản đồ chú ý', 'Bộ dữ liệu chuẩn ISIC', 'Báo cáo PDF & gửi Email'],
                'medical_notice': 'Kết quả phân tích chỉ mang tính chất sàng lọc tham khảo, không phải chẩn đoán y khoa và không thay thế tư vấn trực tiếp với bác sĩ.',
                'tagline': 'Sàng lọc ung thư da bằng AI',
            },
        },
        'en': {
            'hero': {'primary_cta': 'Analyze images', 'secondary_cta': 'Core technology'},
            'features': {
                'eyebrow': 'Core technology', 'title': 'Core features of DermaScan AI',
                'lead': 'Explainable AI-powered skin lesion screening.',
                'items': [
                    {'badge': 'Deep learning', 'title': 'EfficientNet-B0 model', 'description': 'Dermoscopic image classification.'},
                    {'badge': 'Explainability', 'title': 'Grad-CAM visualization', 'description': 'Areas the model focuses on.'},
                    {'badge': 'International data', 'title': 'ISIC dataset', 'description': 'Expert-annotated skin lesion images.'},
                ],
            },
            'footer_extra': {
                'about': 'AI-powered screening assistance for dermatology professionals using EfficientNet-B0 and Grad-CAM.',
                'technology': ['EfficientNet-B0 classification', 'Grad-CAM visual explanations', 'ISIC dataset', 'PDF reports and email'],
                'medical_notice': 'Results are for preliminary screening only, are not a medical diagnosis and do not replace professional medical advice.',
                'tagline': 'AI-powered skin cancer screening',
            },
        },
        'social_links': {'google': '', 'linkedin': '', 'x': '', 'github': ''},
    }
    ASSET_FIELDS = {'logo_path', 'favicon_path'}
    ASSET_SUFFIXES = {'.gif', '.ico', '.jpeg', '.jpg', '.png', '.webp'}
    FALLBACKS = {
        'site_name': 'DermaScan AI',
        'logo_path': 'skin_cancer/webapp/assets/dermascan_logo.png',
        'favicon_path': 'skin_cancer/webapp/assets/dermascan_logo.png',
        'footer_title': 'DermaScan AI',
        'footer_description': 'Phân loại tổn thương da bằng EfficientNet',
        'phone': '',
        'email': '',
        'address': '',
        'facebook_url': '',
        'copyright_text': '© 2026 DermaScan AI',
        'homepage_config': HOMEPAGE_DEFAULTS,
    }
    LIMITS = {
        'site_name': 150,
        'logo_path': 500,
        'favicon_path': 500,
        'footer_title': 255,
        'footer_description': 10000,
        'phone': 30,
        'email': 254,
        'address': 500,
        'facebook_url': 500,
        'copyright_text': 255,
    }

    def __init__(self, app):
        self.app = app

    def get_record(self):
        return db.session.get(SiteSetting, 1)

    def resolve(self):
        setting = self.get_record()
        values = {
            'id': setting.id if setting else None,
            **self._effective_values(setting),
        }
        values['logo_url'] = '/api/site-settings/assets/logo'
        values['favicon_url'] = '/api/site-settings/assets/favicon'
        return values

    def serialize(self, setting=None, include_admin=False):
        if setting is None:
            setting = self.get_record()
        result = {
            'id': setting.id if setting else None,
            **self._effective_values(setting),
            'logo_url': '/api/site-settings/assets/logo',
            'favicon_url': '/api/site-settings/assets/favicon',
        }
        if include_admin:
            result.update({
                'updated_by': setting.updated_by if setting else None,
                'updated_at': setting.updated_at.isoformat() if setting and setting.updated_at else None,
            })
        return result

    def validate_payload(self, payload):
        if not isinstance(payload, dict):
            raise SiteSettingsValidationError('Payload site settings không hợp lệ.')
        unknown = set(payload) - set(self.FIELDS)
        if unknown:
            raise SiteSettingsValidationError('Payload chứa field không được phép.')

        result = {}
        for name, value in payload.items():
            if name == 'homepage_config':
                result[name] = self._homepage_config(value)
            elif name in self.ASSET_FIELDS:
                result[name] = self._asset_value(value, name)
            elif name == 'facebook_url':
                result[name] = self._facebook_url(value)
            elif name == 'email':
                result[name] = self._email(value)
            else:
                result[name] = self._string(value, name, self.LIMITS[name], optional=name != 'site_name')

        if 'site_name' in result and result['site_name'] is None:
            raise SiteSettingsValidationError('site_name là bắt buộc.')
        return result

    def resolve_asset_path(self, path_value):
        if not isinstance(path_value, str) or not path_value.strip():
            raise SiteSettingsValidationError('Đường dẫn asset không hợp lệ.')
        raw_value = path_value.strip()
        raw = Path(raw_value)
        windows = PureWindowsPath(raw_value)
        if raw.is_absolute() or windows.is_absolute() or windows.drive or '..' in raw.parts or '..' in windows.parts:
            raise SiteSettingsValidationError('Đường dẫn asset không an toàn.')
        if raw.suffix.lower() not in self.ASSET_SUFFIXES:
            raise SiteSettingsValidationError('Định dạng asset không được hỗ trợ.')

        roots = [Path(self.app.config['PROJECT_ROOT']), Path(self.app.instance_path)]
        for root_value in roots:
            root = root_value.resolve()
            candidate = (root / raw).resolve()
            if candidate.is_relative_to(root) and candidate.is_file():
                return candidate
        raise SiteSettingsValidationError('File asset không tồn tại hoặc không hợp lệ.')

    def _effective_values(self, setting):
        values = {}
        for name in self.FIELDS:
            value = getattr(setting, name, None) if setting else None
            fallback = self.FALLBACKS[name]
            if value in (None, ''):
                value = fallback
            if name == 'homepage_config':
                value = deepcopy(value)
            if name in self.ASSET_FIELDS:
                try:
                    self.resolve_asset_path(value)
                except SiteSettingsValidationError:
                    value = fallback
            values[name] = value
        return values

    @classmethod
    def _homepage_config(cls, value):
        if not isinstance(value, dict) or set(value) - {'vi', 'en', 'social_links'}:
            raise SiteSettingsValidationError('homepage_config phải là cấu hình hợp lệ.')
        result = deepcopy(cls.HOMEPAGE_DEFAULTS)
        for language in ('vi', 'en'):
            if language not in value:
                continue
            content = value[language]
            if not isinstance(content, dict) or set(content) - {'hero', 'features', 'footer_extra'}:
                raise SiteSettingsValidationError(f'Nội dung {language} không hợp lệ.')
            for section in ('hero', 'features', 'footer_extra'):
                if section not in content:
                    continue
                data = content[section]
                defaults = result[language][section]
                if not isinstance(data, dict) or set(data) - set(defaults):
                    raise SiteSettingsValidationError(f'Mục {section} không hợp lệ.')
                for key, item in data.items():
                    if key == 'items':
                        if not isinstance(item, list) or len(item) != 3:
                            raise SiteSettingsValidationError('Phải có đúng 3 khối tính năng.')
                        for index, feature in enumerate(item):
                            if not isinstance(feature, dict) or set(feature) != {'badge', 'title', 'description'}:
                                raise SiteSettingsValidationError('Nội dung tính năng không hợp lệ.')
                            defaults['items'][index] = {
                                name: cls._required_text(feature[name], 500 if name == 'description' else 150)
                                for name in ('badge', 'title', 'description')
                            }
                    elif key == 'technology':
                        if not isinstance(item, list) or len(item) != 4:
                            raise SiteSettingsValidationError('Phải có đúng 4 nội dung công nghệ.')
                        defaults[key] = [cls._required_text(entry, 300) for entry in item]
                    else:
                        limit = 1200 if key in ('about', 'medical_notice') else 500
                        checked = cls._required_text(item, limit)
                        if key == 'medical_notice' and not (
                            ('không thay thế' in checked.lower()) if language == 'vi'
                            else ('not replace' in checked.lower())
                        ):
                            raise SiteSettingsValidationError('Lưu ý y khoa phải giữ nội dung không thay thế tư vấn bác sĩ.')
                        defaults[key] = checked
        if 'social_links' in value:
            links = value['social_links']
            if not isinstance(links, dict) or set(links) - set(result['social_links']):
                raise SiteSettingsValidationError('Danh sách mạng xã hội không hợp lệ.')
            for name, url in links.items():
                result['social_links'][name] = cls._optional_https(url)
        return result

    @staticmethod
    def _required_text(value, maximum):
        if not isinstance(value, str) or not value.strip() or len(value.strip()) > maximum:
            raise SiteSettingsValidationError('Nội dung không hợp lệ hoặc quá dài.')
        return value.strip()

    @staticmethod
    def _optional_https(value):
        if value in ('', None):
            return ''
        if not isinstance(value, str) or len(value) > 500:
            raise SiteSettingsValidationError('Đường dẫn mạng xã hội không hợp lệ.')
        parsed = urlparse(value.strip())
        if parsed.scheme != 'https' or not parsed.netloc or parsed.username or parsed.password:
            raise SiteSettingsValidationError('Liên kết mạng xã hội phải là HTTPS hợp lệ.')
        return value.strip()

    def _asset_value(self, value, name):
        value = self._string(value, name, self.LIMITS[name], optional=True)
        if value is None:
            return None
        self._validate_relative_asset(value)
        return value

    @staticmethod
    def _validate_relative_asset(value):
        raw = Path(value)
        windows = PureWindowsPath(value)
        if (raw.is_absolute() or windows.is_absolute() or windows.drive
                or '..' in raw.parts or '..' in windows.parts):
            raise SiteSettingsValidationError('Đường dẫn asset không an toàn.')
        if urlparse(value).scheme:
            raise SiteSettingsValidationError('Đường dẫn asset không được là URL.')

    @staticmethod
    def _email(value):
        if value in (None, ''):
            return None
        if not isinstance(value, str) or len(value.strip()) > 254:
            raise SiteSettingsValidationError('email không hợp lệ.')
        value = value.strip()
        local, separator, domain = value.rpartition('@')
        if not separator or not local or not domain or any(char.isspace() for char in value) or '.' not in domain:
            raise SiteSettingsValidationError('email không hợp lệ.')
        return value

    @staticmethod
    def _facebook_url(value):
        if value in (None, ''):
            return None
        if not isinstance(value, str) or len(value.strip()) > 500:
            raise SiteSettingsValidationError('facebook_url không hợp lệ.')
        value = value.strip()
        parsed = urlparse(value)
        if parsed.scheme.lower() not in {'http', 'https'} or not parsed.netloc:
            raise SiteSettingsValidationError('facebook_url phải là URL http(s).')
        return value

    @staticmethod
    def _string(value, name, limit, optional=False):
        if value in (None, '') and optional:
            return None
        if not isinstance(value, str):
            raise SiteSettingsValidationError(f'{name} phải là chuỗi.')
        value = value.strip()
        if not value and not optional:
            raise SiteSettingsValidationError(f'{name} là bắt buộc.')
        if len(value) > limit:
            raise SiteSettingsValidationError(f'{name} vượt quá giới hạn ký tự.')
        return value