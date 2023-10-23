# TODO: AI审核

# 第三方库导入
from flask import Blueprint, jsonify, request
# 应用/模块内部导入
from extensions import mongo


bp = Blueprint('ai', __name__, url_prefix='/api/ai')


@bp.route('/video', methods=['POST'])
def ai_video():
    print(request.get_json())
    return jsonify({"message": "数据已接收"})


@bp.route('/image', methods=['POST'])
def ai_image():
    print(request.get_json())
    return jsonify({"message": "数据已接收"})