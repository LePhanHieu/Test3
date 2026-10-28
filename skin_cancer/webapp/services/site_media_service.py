"""An isolated, validated image library for editable public-site artwork."""
from io import BytesIO
from pathlib import Path
from urllib.parse import quote
from uuid import uuid4

from PIL import Image, ImageOps, UnidentifiedImageError


class SiteMediaError(ValueError):
    pass


class SiteMediaService:
    KINDS = frozenset({'logos', 'favicons', 'banners'})
    ACCEPTED = frozenset({'.jpg', '.jpeg', '.png', '.webp', '.ico'})
    MAX_BYTES = 5 * 1024 * 1024
    MAX_SIDE = 5000

    def __init__(self, app):
        self.root = Path(app.instance_path).resolve()
        self.project = Path(app.config['PROJECT_ROOT']).resolve()
        self.library = self.root / 'site_media'
        self.assets = self.project / 'skin_cancer' / 'webapp' / 'assets'

    def list_images(self):
        items = []
        for source, base in (('Có sẵn', self.assets), ('Đã upload', self.library)):
            if not base.is_dir():
                continue
            for file in sorted(base.rglob('*')):
                if not file.is_file() or file.suffix.lower() not in self.ACCEPTED:
                    continue
                if source == 'Đã upload' and file.parent.name not in self.KINDS:
                    continue
                path = file.relative_to(self.project if source == 'Có sẵn' else self.root).as_posix()
                items.append({'name': file.name, 'path': path, 'source': source,
                              'image_url': '/api/admin/site-media/image?path=' + quote(path)})
        return items

    def resolve(self, relative_path):
        if not isinstance(relative_path, str) or not relative_path:
            raise SiteMediaError('Đường dẫn ảnh không hợp lệ.')
        # Only artwork managed by the site may be selected or previewed.
        candidates = self.list_images()
        if relative_path not in {item['path'] for item in candidates}:
            raise SiteMediaError('Ảnh không thuộc thư viện trang chủ.')
        for root in (self.project, self.root):
            candidate = (root / relative_path).resolve()
            if candidate.is_relative_to(root) and candidate.is_file():
                return candidate
        raise SiteMediaError('Không tìm thấy ảnh.')

    def upload(self, uploaded, kind):
        if kind not in self.KINDS or uploaded is None:
            raise SiteMediaError('Loại hình ảnh không hợp lệ.')
        suffix = Path(uploaded.filename or '').suffix.lower()
        if suffix not in self.ACCEPTED:
            raise SiteMediaError('Chỉ hỗ trợ JPG, PNG, WEBP hoặc ICO.')
        contents = uploaded.stream.read(self.MAX_BYTES + 1)
        if len(contents) > self.MAX_BYTES or not contents:
            raise SiteMediaError('Ảnh rỗng hoặc vượt quá 5 MB.')
        try:
            with Image.open(BytesIO(contents)) as source:
                if source.format not in {'JPEG', 'PNG', 'WEBP', 'ICO'}:
                    raise SiteMediaError('Nội dung file không phải ảnh được hỗ trợ.')
                source.verify()
            with Image.open(BytesIO(contents)) as source:
                if max(source.size) > self.MAX_SIDE or min(source.size) < 1:
                    raise SiteMediaError('Kích thước ảnh không hợp lệ.')
                image = ImageOps.exif_transpose(source)
                if image.mode not in ('RGB', 'RGBA'):
                    image = image.convert('RGBA' if 'A' in image.getbands() else 'RGB')
                output = BytesIO()
                image.save(output, format='PNG', optimize=True)
        except (UnidentifiedImageError, OSError, ValueError, Image.DecompressionBombError) as error:
            raise SiteMediaError('Không thể đọc hoặc xử lý hình ảnh.') from error
        if output.tell() > 12 * 1024 * 1024:
            raise SiteMediaError('Ảnh sau xử lý quá lớn.')

        destination = self.library / kind
        destination.mkdir(parents=True, exist_ok=True)
        filename = uuid4().hex + '.png'
        (destination / filename).write_bytes(output.getvalue())
        return f'site_media/{kind}/{filename}'