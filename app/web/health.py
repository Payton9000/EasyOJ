"""Unauthenticated readiness endpoint used by the local Windows deployer."""

from flask import Blueprint
from flask import current_app
from flask import jsonify
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError

from app import db

HEALTH_MARKER = {'service': 'easyoj', 'status': 'ok', 'version': 1}
NOT_READY_MARKER = {'service': 'easyoj', 'status': 'not_ready', 'version': 1}
health_bp = Blueprint('health', __name__)


@health_bp.get('/healthz')
def healthz():
    """Return 200 only after the database and judge workers are ready."""
    try:
        db.session.execute(text('SELECT 1'))
        database_ready = True
    except SQLAlchemyError:
        database_ready = False

    engine = getattr(current_app, 'judge_engine', None)
    judge_ready = bool(engine and getattr(engine, 'is_running', False))
    if judge_ready:
        workers = getattr(engine, 'workers', ())
        judge_ready = any(getattr(worker, 'is_alive', lambda: False)() for worker in workers)

    if database_ready and judge_ready:
        return jsonify(HEALTH_MARKER), 200
    return jsonify(NOT_READY_MARKER), 503
