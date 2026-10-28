from datetime import datetime, timezone
from ..extensions import db


def utcnow():
    """Store UTC without offset in SQLite; serialize as UTC at the API boundary."""
    return datetime.now(timezone.utc).replace(tzinfo=None)


class Created:
    created_at = db.Column(db.DateTime, nullable=False, default=utcnow, server_default=db.func.current_timestamp())


class Timestamps(Created):
    updated_at = db.Column(db.DateTime, nullable=False, default=utcnow, onupdate=utcnow, server_default=db.func.current_timestamp())


def fk(table):
    return db.ForeignKey(f'{table}.id', ondelete='RESTRICT')
