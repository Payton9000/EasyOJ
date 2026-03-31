from functools import wraps
from flask import abort, redirect, url_for, jsonify, request
from flask_login import current_user


def admin_required(view_func):
    """管理员权限装饰器
    
    组合 @login_required 和管理员权限检查
    - 如果未登录：重定向到登录页（web请求）或返回401 JSON（API请求）
    - 如果非管理员：abort(403)
    """
    @wraps(view_func)
    def decorated_function(*args, **kwargs):
        # 检查登录状态
        if not current_user.is_authenticated:
            # 判断是否为API请求
            if request.path.startswith('/api'):
                return jsonify({'code': 401, 'message': 'Authentication required'}), 401
            return redirect(url_for('web.login'))
        
        # 检查管理员权限
        if not current_user.is_admin:
            abort(403)
        
        return view_func(*args, **kwargs)
    
    return decorated_function
