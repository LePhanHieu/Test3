from ..extensions import db
from .base import Created, Timestamps, fk


class Analysis(Created, db.Model):
    __tablename__ = 'analyses'
    __table_args__ = (
        db.UniqueConstraint('id', 'case_id'),
        db.ForeignKeyConstraint(['case_image_id', 'case_id'], ['case_images.id', 'case_images.case_id'], ondelete='RESTRICT'),
        db.CheckConstraint("status IN ('PENDING','PROCESSING','COMPLETED','FAILED')", name='status'),
        db.CheckConstraint('lesion_area_px >= 0 AND lesion_perimeter_px >= 0 AND lesion_ratio >= 0 AND lesion_ratio <= 1', name='measurement'),
        db.CheckConstraint('bbox_x >= 0 AND bbox_y >= 0 AND bbox_width > 0 AND bbox_height > 0', name='bbox'),
    )
    id = db.Column(db.Integer, primary_key=True)
    case_id = db.Column(db.Integer, fk('cases'), nullable=False, index=True)
    case_image_id = db.Column(db.Integer, nullable=False, index=True)
    gradcam_path = db.Column(db.String(500))
    lesion_area_px = db.Column(db.Float)
    lesion_perimeter_px = db.Column(db.Float)
    lesion_ratio = db.Column(db.Float)
    bbox_x = db.Column(db.Integer)
    bbox_y = db.Column(db.Integer)
    bbox_width = db.Column(db.Integer)
    bbox_height = db.Column(db.Integer)
    contour_path = db.Column(db.String(500))
    status = db.Column(db.String(20), nullable=False, default='PENDING', server_default='PENDING')
    error_message = db.Column(db.Text)
    started_at = db.Column(db.DateTime)
    completed_at = db.Column(db.DateTime)
    image = db.relationship('CaseImage', foreign_keys=[case_image_id], back_populates='analyses')
    case = db.relationship('Case', foreign_keys=[case_id], back_populates='analyses')
    results = db.relationship('AnalysisResult', back_populates='analysis', passive_deletes='all')
    reviews = db.relationship('DoctorReview', foreign_keys='DoctorReview.analysis_id', back_populates='analysis', passive_deletes='all')
    reports = db.relationship('Report', foreign_keys='Report.analysis_id', back_populates='analysis', passive_deletes='all')


class AnalysisResult(Created, db.Model):
    __tablename__ = 'analysis_results'
    __table_args__ = (
        db.CheckConstraint('binary_result IN (0,1)', name='binary_result'),
        db.CheckConstraint('binary_probability >= 0 AND binary_probability <= 1', name='binary_probability'),
        db.CheckConstraint('predicted_probability >= 0 AND predicted_probability <= 1', name='predicted_probability'),
        db.CheckConstraint('inference_time_ms >= 0', name='inference_time'),
    )
    id = db.Column(db.Integer, primary_key=True)
    analysis_id = db.Column(db.Integer, fk('analyses'), nullable=False, index=True)
    model_name = db.Column(db.String(100), nullable=False)
    binary_result = db.Column(db.Integer)
    binary_probability = db.Column(db.Float)
    predicted_class = db.Column(db.String(30))
    predicted_probability = db.Column(db.Float)
    class_probabilities = db.Column(db.JSON)
    inference_time_ms = db.Column(db.Float)
    analysis = db.relationship('Analysis', back_populates='results')


class DoctorReview(Timestamps, db.Model):
    __tablename__ = 'doctor_reviews'
    __table_args__ = (
        db.ForeignKeyConstraint(['analysis_id','case_id'], ['analyses.id','analyses.case_id'], ondelete='RESTRICT'),
        db.CheckConstraint("review_status IN ('DRAFT','REVIEWED')", name='status'),
    )
    id = db.Column(db.Integer, primary_key=True)
    case_id = db.Column(db.Integer, fk('cases'), nullable=False, index=True)
    analysis_id = db.Column(db.Integer, index=True)
    doctor_id = db.Column(db.Integer, fk('users'), nullable=False)
    clinical_note = db.Column(db.Text)
    doctor_conclusion = db.Column(db.Text)
    recommendation = db.Column(db.Text)
    review_status = db.Column(db.String(20), nullable=False, default='DRAFT', server_default='DRAFT')
    case = db.relationship('Case', foreign_keys=[case_id], back_populates='reviews')
    analysis = db.relationship('Analysis', foreign_keys=[analysis_id], back_populates='reviews')
    doctor = db.relationship('User')
