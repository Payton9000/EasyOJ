from functools import wraps

from flask import abort
from flask import jsonify
from flask import redirect
from flask import request
from flask import url_for
from flask_login import current_user


def admin_required(view_func):
    """管理员权限装饰器

    组合 @login_required 和管理员权限检查
    - 如果未登录：重定向到登录页（web请求）或返回401 JSON（API/Judge请求）
    - 如果非管理员：abort(403)
    """

    @wraps(view_func)
    def decorated_function(*args, **kwargs):
        if not current_user.is_authenticated:
            if request.path.startswith('/api') or request.path.startswith('/judge'):
                return jsonify({'code': 401, 'message': 'Authentication required'}), 401
            return redirect(url_for('web.login'))

        if not current_user.is_admin:
            abort(403)

        return view_func(*args, **kwargs)

    return decorated_function
