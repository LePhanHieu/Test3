"""Task 8: Cache kết quả theo hash ảnh.

Hỗ trợ 2 chế độ:
1. SQLite Native Disk Cache (Mặc định - KHÔNG CẦN DOCKER HAY REDIS):
   - Lưu trữ trực tiếp trên đĩa tại `instance/cache.db`.
   - Sử dụng thư viện có sẵn trong Python (sqlite3), không cần cài đặt thêm bất kỳ công cụ nào.
   - Bền vững qua các lần khởi động lại server, hỗ trợ thời hạn hết hạn (TTL 7 ngày).
   - Đảm bảo an toàn đa luồng và đa tiến trình nhờ chế độ WAL (Write-Ahead Logging).

2. Redis Cache (Tuỳ chọn nếu môi trường có sẵn Redis):
   - Tự động kết nối nếu Redis đang bật, nếu tắt hoặc lỗi sẽ tự động chuyển về SQLite.
"""

import hashlib
import json
import os
import sqlite3
import time
from pathlib import Path

try:
    import redis
except ImportError:
    redis = None

# Đường dẫn file cache SQLite nằm trong thư mục instance/ của project
PROJECT_ROOT = Path(__file__).resolve().parents[3]
CACHE_DB_PATH = PROJECT_ROOT / "instance" / "cache.db"

REDIS_URL = os.environ.get("REDIS_URL", "redis://localhost:6379/0")
CACHE_TTL = 7 * 24 * 3600  # Giữ kết quả trong 7 ngày
CACHE_VERSION = "v1"

_client = None
_mem_cache = {}
_sqlite_initialized = False


def _init_sqlite_cache():
    """Khởi tạo bảng cache trong SQLite nếu chưa có."""
    global _sqlite_initialized
    if _sqlite_initialized:
        return
    try:
        CACHE_DB_PATH.parent.mkdir(parents=True, exist_ok=True)
        with sqlite3.connect(str(CACHE_DB_PATH), timeout=10.0) as conn:
            conn.execute("PRAGMA journal_mode=WAL")
            conn.execute("""
                CREATE TABLE IF NOT EXISTS cache_store (
                    key TEXT PRIMARY KEY,
                    value TEXT NOT NULL,
                    expires_at REAL NOT NULL
                )
            """)
            conn.execute("CREATE INDEX IF NOT EXISTS idx_cache_expires ON cache_store(expires_at)")
        _sqlite_initialized = True
    except Exception:
        pass


def _get_client():
    """Lấy kết nối Redis nếu khả dụng (với timeout ngắn 0.3s để không làm chậm app)."""
    global _client
    if redis is None:
        return None
    if _client is None:
        try:
            client = redis.Redis.from_url(
                REDIS_URL,
                decode_responses=True,
                socket_connect_timeout=0.3,
                socket_timeout=0.5,
            )
            # Thử ping nhẹ để kiểm tra Redis có thực sự đang chạy không
            client.ping()
            _client = client
        except Exception:
            _client = None
            return None
    return _client


def image_hash(pil_img):
    """Hash theo nội dung pixel + loại model đang dùng (torch / onnx / onnx_int8)."""
    backend = os.environ.get("MODEL_BACKEND", "torch")
    rgb = pil_img.convert("RGB")
    h = hashlib.sha256()
    h.update(f"{CACHE_VERSION}|{backend}|{rgb.size}".encode())
    h.update(rgb.tobytes())
    return f"analysis-cache:{h.hexdigest()}"


def get_cached(key):
    """Lấy dữ liệu cache từ RAM -> Redis -> SQLite."""
    now = time.time()

    # 1. Kiểm tra RAM cache trước (siêu nhanh)
    if key in _mem_cache:
        data, exp = _mem_cache[key]
        if exp > now:
            return data
        else:
            _mem_cache.pop(key, None)

    # 2. Kiểm tra Redis nếu có
    client = _get_client()
    if client is not None:
        try:
            raw = client.get(key)
            if raw:
                val = json.loads(raw)
                _mem_cache[key] = (val, now + CACHE_TTL)
                return val
        except Exception:
            pass

    # 3. Kiểm tra SQLite Disk Cache (Không cần Docker/Redis)
    _init_sqlite_cache()
    try:
        with sqlite3.connect(str(CACHE_DB_PATH), timeout=5.0) as conn:
            cur = conn.execute("SELECT value, expires_at FROM cache_store WHERE key = ?", (key,))
            row = cur.fetchone()
            if row:
                val_str, expires_at = row
                if expires_at > now:
                    val = json.loads(val_str)
                    _mem_cache[key] = (val, expires_at)
                    return val
                else:
                    conn.execute("DELETE FROM cache_store WHERE key = ?", (key,))
    except Exception:
        pass

    return None


def save_cached(key, value):
    """Lưu dữ liệu cache vào RAM, SQLite và Redis (nếu có)."""
    now = time.time()
    expires_at = now + CACHE_TTL

    # 1. Lưu RAM cache
    if len(_mem_cache) >= 200:
        _mem_cache.pop(next(iter(_mem_cache)), None)
    _mem_cache[key] = (value, expires_at)

    val_json = json.dumps(value)

    # 2. Lưu vào SQLite Disk Cache (hoạt động độc lập, không cần Docker)
    _init_sqlite_cache()
    try:
        with sqlite3.connect(str(CACHE_DB_PATH), timeout=5.0) as conn:
            conn.execute("""
                INSERT INTO cache_store (key, value, expires_at)
                VALUES (?, ?, ?)
                ON CONFLICT(key) DO UPDATE SET value=excluded.value, expires_at=excluded.expires_at
            """, (key, val_json, expires_at))
    except Exception:
        pass

    # 3. Lưu vào Redis nếu có
    client = _get_client()
    if client is not None:
        try:
            client.setex(key, CACHE_TTL, val_json)
        except Exception:
            pass


def is_redis_available():
    """Kiểm tra Redis có thực sự đang chạy hay không."""
    return _get_client() is not None


def get_cache_backend_name():
    """Trả về tên backend cache đang được sử dụng."""
    if is_redis_available():
        return "Redis (Docker)"
    return "SQLite Disk Cache (Native - Không cần Docker)"
