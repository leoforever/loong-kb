"""
Flask application entry point
"""
import logging
import os
from flask import Flask, session, redirect, url_for, render_template, g, request

os.makedirs(os.path.join(os.path.dirname(__file__), 'cache'), exist_ok=True)
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(name)s: %(message)s',
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler(os.path.join(os.path.dirname(__file__), 'cache', 'app.log')),
    ]
)
logger = logging.getLogger(__name__)


def create_app():
    app = Flask(__name__)
    app.secret_key = os.environ.get('SECRET_KEY', 'loong-kb-secret-2026')
    app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024

    from app.models import init_db
    init_db()

    # Auto-sync KBs from Dify on startup
    from app.services.dify_sync import auto_sync_on_startup
    auto_sync_on_startup()

    from app.routes import auth, qa, admin
    app.register_blueprint(auth.bp)
    app.register_blueprint(qa.bp)
    app.register_blueprint(admin.bp)

    @app.before_request
    def load_current_user():
        g.user = None
        g.is_admin = False
        user_id = session.get('user_id')
        if user_id:
            from app.models import get_user_by_id, get_user_roles as _gur
            g.user = get_user_by_id(user_id)
            g.is_admin = 'admin' in _gur(user_id)

    @app.context_processor
    def inject_globals():
        return dict(is_admin=getattr(g, 'is_admin', False), request=request)

    @app.template_global()
    def get_user_roles(user_id):
        from app.models import get_user_roles as _gur
        return _gur(user_id)

    @app.route('/')
    def index():
        if not session.get('user_id'):
            return redirect(url_for('auth.login'))
        return redirect(url_for('qa.index'))

    logger.info("Loong KB 应用已启动")
    return app


if __name__ == '__main__':
    from app.config import get_server_config
    cfg = get_server_config()
    app = create_app()
    app.run(host=cfg['host'], port=cfg['port'], debug=False)