from ..extensions import db
from .base import Timestamps, fk, utcnow


class SiteSetting(db.Model):
    __tablename__ = 'site_settings'
    __table_args__ = (db.CheckConstraint('id = 1', name='singleton'),)
    id = db.Column(db.Integer, primary_key=True, default=1)
    site_name = db.Column(db.String(150), nullable=False, default='DermaScan AI')
    logo_path = db.Column(db.String(500))
    favicon_path = db.Column(db.String(500))
    footer_title = db.Column(db.String(255))
    footer_description = db.Column(db.Text)
    phone = db.Column(db.String(30))
    email = db.Column(db.String(254))
    address = db.Column(db.String(500))
    facebook_url = db.Column(db.String(500))
    copyright_text = db.Column(db.String(255))
    homepage_config = db.Column(db.JSON, nullable=True)
    updated_by = db.Column(db.Integer, fk('users'))
    updated_at = db.Column(db.DateTime, nullable=False, default=utcnow, onupdate=utcnow, server_default=db.func.current_timestamp())
    updater = db.relationship('User')


class Slide(Timestamps, db.Model):
    __tablename__ = 'slides'
    __table_args__ = (db.CheckConstraint('end_at IS NULL OR start_at IS NULL OR end_at >= start_at', name='schedule'),)
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(255), nullable=False)
    subtitle = db.Column(db.Text)
    image_path = db.Column(db.String(500), nullable=False)
    button_text = db.Column(db.String(100))
    button_url = db.Column(db.String(500))
    display_order = db.Column(db.Integer, nullable=False, default=0, server_default='0', index=True)
    is_active = db.Column(db.Boolean, nullable=False, default=True, server_default=db.true())
    start_at = db.Column(db.DateTime)
    end_at = db.Column(db.DateTime)
    created_by = db.Column(db.Integer, fk('users'), nullable=False)
    creator = db.relationship('User')