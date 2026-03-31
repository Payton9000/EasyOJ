from flask import Flask
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager
from flask_migrate import Migrate

from app.config import config

db = SQLAlchemy()
login_manager = LoginManager()
migrate = Migrate()


def create_app(config_name='default'):
    app = Flask(__name__)
    app.config.from_object(config[config_name])

    # Initialize extensions
    db.init_app(app)
    login_manager.init_app(app)
    migrate.init_app(app, db)

    login_manager.login_view = 'web.login'
    login_manager.login_message_category = 'error'

    @login_manager.user_loader
    def load_user(user_id):
        from app.models.user import User
        return User.query.get(int(user_id))

    # Register blueprints
    from app.web import web_bp
    app.register_blueprint(web_bp)

    from app.api import api_bp
    app.register_blueprint(api_bp, url_prefix='/api')

    from app.judge import judge_bp
    app.register_blueprint(judge_bp, url_prefix='/judge')

    with app.app_context():
        db.create_all()

    # Initialize and start judge engine
    from app.judge.engine import JudgeEngine
    judge_engine = JudgeEngine(app)
    app.judge_engine = judge_engine

    if not app.config.get('TESTING'):
        judge_engine.start()

    @app.teardown_appcontext
    def shutdown_judge_engine(exception=None):
        pass  # Engine runs as daemon threads; stop on process exit

    return app
