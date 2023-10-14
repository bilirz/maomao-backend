# 标准库导入
from functools import wraps
# 第三方库导入
from flask import jsonify, session


# 判断是否登录
def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user' not in session:
            return jsonify({"message": "请先登录"}), 401
        return f(*args, **kwargs)
    return decorated_function
