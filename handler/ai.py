# 第三方库导入
from flask import Blueprint, jsonify, request

bp = Blueprint('ai', __name__, url_prefix='/api/ai')


@bp.route('/video', methods=['POST'])
def ai_video():
    """接收视频数据"""
    video_data = request.get_json()
    print(video_data)

    return jsonify({"message": "数据已接收"}), 200


@bp.route('/image', methods=['POST'])
def ai_image():
    """接收图片数据"""
    image_data = request.get_json()
    print(image_data)

    return jsonify({"message": "数据已接收"}), 200
