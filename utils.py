# 标准库导入
import time
from functools import wraps
# 第三方库导入
from flask import jsonify, session
# 应用/模块内部导入
from extensions import mongo


def login_required(f):
    """判断是否登录"""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user' not in session:
            return jsonify({"message": "请先登录"}), 401
        return f(*args, **kwargs)
    return decorated_function


def admin_required(f):
    """判断是否是管理员"""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        uid = session['user']['uid']
        user = mongo.db.user.find_one({"uid": uid})
        if not user or user.get("status", 0) != 1:
            return jsonify({"message": "您没有权限进行此操作"}), 403
        return f(*args, **kwargs)
    return decorated_function


def adjust_points_and_exp(uid, points, exp=0, reason=''):
    """为用户调整积分和经验"""

    user = mongo.db.user.find_one({"uid": uid})
    if not user:
        return {"status": "error", "message": "用户不存在"}

    # 判断用户积分是否足够扣除
    if points < 0 and abs(points) > user["checkin"]["points"]:
        return {"status": "error", "message": f"积分不足，{reason}需要消耗{abs(points)}积分"}

    user["checkin"]["points"] += points
    user["checkin"]["experience"] += exp

    mongo.db.user.update_one({"uid": uid}, {"$set": {
        "checkin.points": user["checkin"]["points"],
        "checkin.experience": user["checkin"]["experience"]
    }})

    # 记录积分和经验的变动
    log = {
        "uid": uid,
        "points_change": points,
        "exp_change": exp,
        "time": time.time(),
        "reason": reason
    }
    mongo.db.point_exp_log.insert_one(log)

    return {"status": "success", "message": "积分和经验调整成功"}


def get_exp_rank(exp=0):
    """获取当前用户的经验值排名"""
    rank = mongo.db.user.count_documents({"checkin.experience": {"$gt": exp}})
    return rank + 1  # 因为count_documents会返回高于给定经验值的用户数，所以需要+1来得到实际的排名


def get_real_ip(request):
    """获取真实IP"""
    forwarded_for = request.headers.get('X-Forwarded-For', '').split(',')
    real_ip = forwarded_for[0].strip(
    ) if forwarded_for else request.remote_addr
    return real_ip
