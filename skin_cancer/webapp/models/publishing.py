from ..extensions import db
from .base import Created, fk


class Report(Created, db.Model):
    __tablename__ = 'reports'
    __table_args__ = (
        db.ForeignKeyConstraint(['analysis_id','case_id'], ['analyses.id','analyses.case_id'], ondelete='RESTRICT'),
        db.UniqueConstraint('case_id','report_version'),
        db.CheckConstraint('report_version > 0', name='version'),
    )
    id = db.Column(db.Integer, primary_key=True)
    case_id = db.Column(db.Integer, fk('cases'), nullable=False, index=True)
    analysis_id = db.Column(db.Integer, index=True)
    pdf_path = db.Column(db.String(500), nullable=False)
    generated_by = db.Column(db.Integer, fk('users'), nullable=False)
    report_version = db.Column(db.Integer, nullable=False)
    case = db.relationship('Case', foreign_keys=[case_id], back_populates='reports')
    analysis = db.relationship('Analysis', foreign_keys=[analysis_id], back_populates='reports')
    generator = db.relationship('User')
    email_logs = db.relationship('EmailLog', back_populates='report', passive_deletes='all')


class EmailLog(Created, db.Model):
    __tablename__ = 'email_logs'
    __table_args__ = (db.CheckConstraint("status IN ('PENDING','SENT','FAILED')", name='status'),)
    id = db.Column(db.Integer, primary_key=True)
    report_id = db.Column(db.Integer, fk('reports'), nullable=False, index=True)
    recipient_email = db.Column(db.String(254), nullable=False)
    subject = db.Column(db.String(255), nullable=False)
    status = db.Column(db.String(20), nullable=False, default='PENDING', server_default='PENDING')
    sent_by = db.Column(db.Integer, fk('users'), nullable=False)
    sent_at = db.Column(db.DateTime)
    error_message = db.Column(db.Text)
    report = db.relationship('Report', back_populates='email_logs')
    sender = db.relationship('User')
