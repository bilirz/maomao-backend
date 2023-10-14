# 标准库导入
import time
import os
# 第三方库导入
from flask import Blueprint, jsonify, request, session, current_app
# 应用/模块内部导入
from extensions import mongo
from utils import login_required, admin_required


bp = Blueprint('admin', __name__, url_prefix='/api/admin')

@bp.route('/hide_video/<int:aid>', methods=['POST'])
@login_required
@admin_required
def hide_video(aid):
    reason = request.json.get('reason')  # 隐藏原因

    result = mongo.db.video.update_one(
        {"aid": aid},
        {
            "$set": {
                "hidden.is_hidden": True,
                "hidden.reason": reason,
                "hidden.grade": 1,
                "hidden.uid": session['user']['uid'],
                "hidden.time": time.time()
            }
        }
    )

    # 重命名 HLS 文件夹
    hls_video_path = os.path.join(current_app.config['HLS_VIDEO_FOLDER'], str(aid))
    if os.path.exists(hls_video_path):
        os.rename(hls_video_path, os.path.join(current_app.config['HLS_VIDEO_FOLDER'], f"{aid}_"))

    # 重命名图片文件
    image_path = os.path.join(current_app.config['IMAGE_UPLOAD_FOLDER'], f"{aid}.jpg")
    if os.path.exists(image_path):
        os.rename(image_path, os.path.join(current_app.config['IMAGE_UPLOAD_FOLDER'], f"{aid}_.jpg"))

    if result.matched_count == 0:
        return jsonify({"message": "视频未找到"}), 404

    return jsonify({"message": "视频已隐藏"})