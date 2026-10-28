"""Task 7: Cấu hình Celery (hàng đợi Redis).

Được bọc try/except an toàn khi môi trường chưa cài đặt celery.
Chạy worker:  celery -A skin_cancer.webapp.celery_app worker --loglevel=info --pool=solo
"""

import os

try:
    from celery import Celery, signals
except ImportError:
    Celery = None
    signals = None

REDIS_URL = os.environ.get("REDIS_URL", "redis://localhost:6379/0")

if Celery is not None:
    celery = Celery(
        "dermascan",
        broker=REDIS_URL,  # nơi xếp hàng các việc cần làm
        backend=REDIS_URL,  # nơi lưu kết quả để web lấy lại
        include=["skin_cancer.webapp.tasks"],
    )

    celery.conf.update(
        task_serializer="json",
        result_serializer="json",
        accept_content=["json"],
        result_expires=3600,  # kết quả giữ 1 giờ
        task_track_started=True,  # có trạng thái STARTED khi worker đang chạy
        worker_prefetch_multiplier=1,  # mỗi lần chỉ lấy 1 việc (việc AI khá nặng)
        broker_connection_retry_on_startup=True,
    )

    @signals.worker_ready.connect
    def preload_models(**kwargs):
        """Nạp model một lần ngay khi worker khởi động, ca đầu tiên không bị chậm."""
        import skin_cancer.webapp.app  # noqa: F401
else:
    celery = None
