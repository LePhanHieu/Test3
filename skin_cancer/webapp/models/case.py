from ..extensions import db
from .base import Timestamps, Created, fk, utcnow


class Case(Timestamps, db.Model):
    __tablename__ = 'cases'

    __table_args__ = (
        db.CheckConstraint(
            "status IN "
            "('CREATED','UPLOADED','ANALYZED','REVIEWED','COMPLETED')",
            name='status',
        ),
        db.CheckConstraint(
            "patient_user_id IS NOT NULL "
            "OR patient_snapshot IS NOT NULL",
            name='patient_source',
        ),
    )

    id = db.Column(
        db.Integer,
        primary_key=True,
    )

    case_code = db.Column(
        db.String(40),
        nullable=False,
        unique=True,
    )

    # Có tài khoản USER -> lưu ID.
    # Bệnh nhân tạm -> NULL.
    patient_user_id = db.Column(
        db.Integer,
        fk('users'),
        nullable=True,
        index=True,
    )

    # Snapshot thông tin bệnh nhân tại thời điểm tạo ca.
    patient_snapshot = db.Column(
        db.JSON,
        nullable=True,
    )

    doctor_id = db.Column(
        db.Integer,
        fk('users'),
        nullable=False,
        index=True,
    )

    lesion_location = db.Column(
        db.String(255),
    )

    status = db.Column(
        db.String(20),
        nullable=False,
        default='CREATED',
        server_default='CREATED',
    )

    patient = db.relationship(
        'User',
        foreign_keys=[patient_user_id],
        back_populates='patient_cases',
    )

    doctor = db.relationship(
        'User',
        foreign_keys=[doctor_id],
        back_populates='assigned_cases',
    )

    images = db.relationship(
        'CaseImage',
        back_populates='case',
        passive_deletes='all',
    )

    batches = db.relationship(
        'UploadBatch',
        back_populates='case',
        passive_deletes='all',
    )

    analyses = db.relationship(
        'Analysis',
        back_populates='case',
        passive_deletes='all',
    )

    reviews = db.relationship(
        'DoctorReview',
        back_populates='case',
        passive_deletes='all',
    )

    reports = db.relationship(
        'Report',
        back_populates='case',
        passive_deletes='all',
    )


class UploadBatch(Created, db.Model):
    __tablename__ = 'upload_batches'
    __table_args__ = (
        db.UniqueConstraint('id', 'case_id'),
        db.CheckConstraint('total_images >= 0 AND success_count >= 0 AND failed_count >= 0 AND success_count + failed_count <= total_images', name='counts'),
        db.CheckConstraint("status IN ('PENDING','PROCESSING','COMPLETED','PARTIAL','FAILED')", name='status'),
    )
    id = db.Column(db.Integer, primary_key=True)
    case_id = db.Column(db.Integer, fk('cases'), nullable=False, index=True)
    doctor_id = db.Column(db.Integer, fk('users'), nullable=False)
    total_images = db.Column(db.Integer, nullable=False, default=0, server_default='0')
    success_count = db.Column(db.Integer, nullable=False, default=0, server_default='0')
    failed_count = db.Column(db.Integer, nullable=False, default=0, server_default='0')
    csv_path = db.Column(db.String(500))
    status = db.Column(db.String(20), nullable=False, default='PENDING', server_default='PENDING')
    item_results = db.Column(db.JSON)  # Reserved for rejected files without CaseImage.
    completed_at = db.Column(db.DateTime)
    case = db.relationship('Case', back_populates='batches')
    doctor = db.relationship('User')
    images = db.relationship('CaseImage', foreign_keys='CaseImage.batch_id', back_populates='batch', passive_deletes='all')


class CaseImage(db.Model):
    __tablename__ = 'case_images'
    __table_args__ = (
        db.UniqueConstraint('id', 'case_id'),
        db.ForeignKeyConstraint(['batch_id', 'case_id'], ['upload_batches.id', 'upload_batches.case_id'], ondelete='RESTRICT'),
        db.CheckConstraint('file_size >= 0', name='file_size'),
        db.CheckConstraint("status IN ('UPLOADED','PROCESSING','COMPLETED','FAILED')", name='status'),
    )
    id = db.Column(db.Integer, primary_key=True)
    case_id = db.Column(db.Integer, fk('cases'), nullable=False, index=True)
    batch_id = db.Column(db.Integer, index=True)
    image_path = db.Column(db.String(500), nullable=False)
    original_filename = db.Column(db.String(255), nullable=False)
    mime_type = db.Column(db.String(100), nullable=False)
    file_size = db.Column(db.Integer, nullable=False)
    sha256_hash = db.Column(db.String(64), index=True)
    perceptual_hash = db.Column(db.String(64))
    focus_region = db.Column(db.JSON)
    uploaded_by = db.Column(db.Integer, fk('users'), nullable=False)
    uploaded_at = db.Column(db.DateTime, nullable=False, default=utcnow, server_default=db.func.current_timestamp())
    status = db.Column(db.String(20), nullable=False, default='UPLOADED', server_default='UPLOADED')
    error_message = db.Column(db.Text)
    case = db.relationship('Case', foreign_keys=[case_id], back_populates='images')
    batch = db.relationship('UploadBatch', foreign_keys=[batch_id], back_populates='images')
    uploader = db.relationship('User')
    analyses = db.relationship('Analysis', foreign_keys='Analysis.case_image_id', back_populates='image', passive_deletes='all')
