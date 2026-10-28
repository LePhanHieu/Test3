from pathlib import Path, PureWindowsPath
from flask import Blueprint, abort, current_app, jsonify, send_file
from ..extensions import db
from ..models import Report
from ..services.access import require_roles, visible_case_or_404

bp = Blueprint('reports', __name__, url_prefix='/api/reports')


def get_visible_report(report_id):
    report = db.session.get(Report, report_id)
    if not report:
        abort(404)
    visible_case_or_404(report.case_id)
    return report


@bp.get('/<int:report_id>')
@require_roles()
def get_report(report_id):
    r = get_visible_report(report_id)
    return jsonify(id=r.id, case_id=r.case_id, analysis_id=r.analysis_id,
                   report_version=r.report_version, generated_by=r.generated_by,
                   download_url=f'/api/reports/{r.id}/download')


@bp.get('/<int:report_id>/download')
@require_roles()
def download(report_id):
    report = get_visible_report(report_id)
    relative = Path(report.pdf_path)
    if relative.is_absolute() or PureWindowsPath(report.pdf_path).drive or '..' in relative.parts:
        abort(404)
    root = Path(current_app.config['REPORT_FOLDER']).resolve()
    path = (root / relative).resolve()
    if not path.is_relative_to(root) or not path.is_file() or path.suffix.lower() != '.pdf':
        abort(404)
    response = send_file(path, mimetype='application/pdf', as_attachment=True,
                        download_name=f'DermaScan_{report.case.case_code}_v{report.report_version}.pdf',
                        conditional=False)
    response.headers['Cache-Control'] = 'private, no-store'
    return response
