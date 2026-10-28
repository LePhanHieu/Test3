"""Unbound extensions, shared by the database CLI and existing AI app."""
import sqlite3
from flask_sqlalchemy import SQLAlchemy
from flask_migrate import Migrate
from flask_login import LoginManager
from flask_wtf.csrf import CSRFProtect
from flask_mail import Mail
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from sqlalchemy import MetaData, event
from sqlalchemy.engine import Engine

metadata = MetaData(naming_convention={
    'ix': 'ix_%(table_name)s_%(column_0_name)s',
    'uq': 'uq_%(table_name)s_%(column_0_name)s',
    'ck': 'ck_%(table_name)s_%(constraint_name)s',
    'fk': 'fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s',
    'pk': 'pk_%(table_name)s',
})
db = SQLAlchemy(metadata=metadata)
migrate = Migrate()
login_manager = LoginManager()
csrf = CSRFProtect()
mail = Mail()
limiter = Limiter(
    key_func=get_remote_address,
    default_limits=[],
)


@event.listens_for(Engine, 'connect')
def enable_sqlite_foreign_keys(connection, _record):
    if not isinstance(connection, sqlite3.Connection):
        return
    # Python 3.11 has no autocommit attribute; 3.12+ may require it for PRAGMA.
    ac = getattr(connection, 'autocommit', None)
    if ac is not None:
        connection.autocommit = True
    try:
        cursor = connection.cursor()
        cursor.execute('PRAGMA foreign_keys=ON')
        cursor.close()
    finally:
        if ac is not None:
            connection.autocommit = ac
