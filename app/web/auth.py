from flask import flash
from flask import redirect
from flask import render_template
from flask import request
from flask import session
from flask import url_for
from flask_login import current_user
from flask_login import login_required
from flask_login import login_user
from flask_login import logout_user

from app.i18n import SUPPORTED_LOCALES
from app.i18n import translate as t
from app.services.account_service import AccountService
from app.web import web_bp


def _account_error(error):
    messages = {
        'Username or email is already registered.': 'flash.account_exists',
        'Current password is incorrect.': 'flash.current_password_invalid',
        'Passwords do not match.': 'flash.password_mismatch',
        'Enter a valid email address.': 'flash.invalid_email',
        'Username must be 3-32 characters using lowercase letters, numbers, _, ., or -.': 'flash.invalid_username',
    }
    message = str(error)
    key = messages.get(message)
    return t(key) if key else message


def _safe_next():
    next_url = request.args.get('next') or ''
    if (
        next_url.startswith('/')
        and not next_url.startswith('//')
        and not next_url.startswith('/\\')
    ):
        return next_url
    return None


@web_bp.route('/login', methods=['GET', 'POST'])
def login():
    if current_user.is_authenticated:
        return redirect(url_for('web.index'))
    if request.method == 'POST':
        username = request.form.get('username', '')
        password = request.form.get('password', '')
        if not username or not password:
            flash(t('flash.login_required'), 'error')
            return redirect(url_for('web.login'))
        user = AccountService.authenticate(username, password)
        if user:
            flashed_messages = session.get('_flashes', [])
            selected_locale = session.get('locale')
            session.clear()
            session['_flashes'] = flashed_messages
            if selected_locale in SUPPORTED_LOCALES:
                session['locale'] = selected_locale
            login_user(user, remember=False)
            if user.must_change_password:
                flash(t('flash.temp_password'), 'info')
                return redirect(url_for('web.change_password'))
            flash(t('flash.welcome', username=user.username), 'success')
            return redirect(_safe_next() or url_for('web.index'))
        flash(t('flash.invalid_credentials'), 'error')
        return redirect(url_for('web.login'))
    return render_template('auth/login.html')


@web_bp.route('/register', methods=['GET', 'POST'])
def register():
    if current_user.is_authenticated:
        return redirect(url_for('web.index'))
    if request.method == 'POST':
        username = request.form.get('username', '')
        email = request.form.get('email', '')
        password = request.form.get('password', '')
        confirm_password = request.form.get('confirm_password', '')
        if not all([username, email, password, confirm_password]):
            flash(t('flash.all_fields_required'), 'error')
            return redirect(url_for('web.register'))
        if password != confirm_password:
            flash(t('flash.password_mismatch'), 'error')
            return redirect(url_for('web.register'))
        try:
            AccountService.register(username, email, password)
        except ValueError as exc:
            flash(_account_error(exc), 'error')
            return redirect(url_for('web.register'))
        flash(t('flash.registration_success'), 'success')
        return redirect(url_for('web.login'))
    return render_template('auth/register.html')


@web_bp.route('/logout', methods=['POST'])
@login_required
def logout():
    logout_user()
    flash(t('flash.logged_out'), 'success')
    return redirect(url_for('web.index'))


@web_bp.route('/change-password', methods=['GET', 'POST'])
@login_required
def change_password():
    if request.method == 'POST':
        try:
            current_password = (
                request.form.get('current_password', '')
                if not current_user.must_change_password
                else None
            )
            AccountService.change_password(
                current_user,
                request.form.get('password', ''),
                request.form.get('confirm_password', ''),
                current_password=current_password,
            )
        except ValueError as exc:
            flash(_account_error(exc), 'error')
            return render_template('auth/change_password.html')
        flash(t('flash.password_changed'), 'success')
        return redirect(url_for('web.index'))
    return render_template('auth/change_password.html')
