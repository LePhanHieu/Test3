"""Register the Phase 1 API, shared by both app entrypoints."""
from flask import jsonify, request
from flask_wtf.csrf import CSRFError
from sqlalchemy.exc import SQLAlchemyError
from werkzeug.exceptions import HTTPException, RequestEntityTooLarge
from .extensions import db, login_manager, csrf, limiter



def register_database_api(app):
    login_manager.init_app(app)
    csrf.init_app(app)
    limiter.init_app(app)
    from .routes.auth import bp as auth_bp
    from .routes.cases import bp as cases_bp
    from .routes.reports import bp as reports_bp
    from .routes.uploads import bp as uploads_bp
    from .routes.measurements import bp as measurements_bp
    from .routes.report_generation import bp as report_generation_bp
    from .routes.report_email import bp as report_email_bp
    from .routes.slides import bp as slides_bp
    from .routes.site_settings import bp as site_settings_bp
    from .routes.admin import bp as admin_bp
    from .routes.comparison import bp as comparison_bp
    from .routes.focus_region import bp as focus_region_bp
    from .routes.timeline import bp as timeline_bp
    from .routes.analysis_status import bp as analysis_status_bp

    app.register_blueprint(auth_bp)
    app.register_blueprint(cases_bp)
    app.register_blueprint(reports_bp)
    app.register_blueprint(uploads_bp)
    app.register_blueprint(measurements_bp)
    app.register_blueprint(report_generation_bp)
    app.register_blueprint(report_email_bp)
    app.register_blueprint(slides_bp)
    app.register_blueprint(site_settings_bp)
    app.register_blueprint(admin_bp)
    app.register_blueprint(comparison_bp)
    app.register_blueprint(focus_region_bp)
    app.register_blueprint(timeline_bp)
    app.register_blueprint(analysis_status_bp)

    @app.errorhandler(CSRFError)
    def csrf_error(_error):
        return jsonify(success=False, message='CSRF token thiếu hoặc hết hạn', error='CSRF token thiếu hoặc hết hạn'), 400

    @app.errorhandler(RequestEntityTooLarge)
    def request_too_large(_error):
        return jsonify(success=False, message='Dung lượng request upload vượt giới hạn',
                       error='Dung lượng request upload vượt giới hạn'), 413

    @app.errorhandler(HTTPException)
    def http_error(error):
        orig = getattr(error, 'original_exception', None)
        if error.code == 500 or orig is not None:
            app.logger.exception('HTTP Exception %s: %s', error.code, orig or error.description)
        return jsonify(success=False, message=error.description, error=error.description), error.code

    @app.errorhandler(Exception)
    def unhandled_error(error):
        app.logger.exception('Unhandled Exception: %s', error)
        return jsonify(success=False, message='Đã xảy ra lỗi trên máy chủ. Vui lòng thử lại sau.', error=str(error)), 500

    @app.errorhandler(SQLAlchemyError)
    def database_error(_error):
        db.session.rollback()
        app.logger.exception('Database operation failed')
        return jsonify(success=False, message='Không thể xử lý dữ liệu'), 500

    @app.after_request
    def private_api_cache(response):
        if request.path.startswith('/api/'):
            response.headers['Cache-Control'] = 'private, no-store'
        return response
