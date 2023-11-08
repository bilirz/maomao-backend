# 标准库导入
import time

# 第三方库导入
from flask import Blueprint, jsonify, request, session

# 应用/模块内部导入
from extensions import mongo
from utils import login_required, admin_required

bp = Blueprint('admin', __name__, url_prefix='/api/admin')


@bp.route('/hide_video/<int:aid>', methods=['POST'])
@login_required
@admin_required
def hide_video(aid):
    """隐藏视频"""
    reason = request.json.get('reason')

    doct = {
        "hidden.is_hidden": True,
        "hidden.reason": reason,
        "hidden.grade": 1,
        "hidden.uid": session.get('user', {}).get('uid'),
        "hidden.time": time.time()
    }

    result = mongo.db.video.update_one({"aid": aid}, {"$set": doct})

    if result.matched_count == 0:
        return jsonify({"message": "视频未找到"}), 404

    return jsonify({"message": "视频已隐藏"})
