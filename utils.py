# 标准库导入
from functools import wraps
# 第三方库导入
from flask import jsonify, session
# 应用/模块内部导入
from extensions import mongo


# 判断是否登录
def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user' not in session:
            return jsonify({"message": "请先登录"}), 401
        return f(*args, **kwargs)
    return decorated_function


def admin_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        uid = session['user']['uid']
        user = mongo.db.user.find_one({"uid": uid})
        if not user or user.get("status", 0) != 1:
            return jsonify({"message": "您没有权限进行此操作"}), 403
        return f(*args, **kwargs)
    return decorated_function
