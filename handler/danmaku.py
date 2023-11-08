# 标准库导入
import time
# 标准库导入
from datetime import datetime
# 第三方库导入
from flask import Blueprint, jsonify, request, session
# 应用/模块内部导入
from extensions import mongo
from utils import login_required, adjust_points_and_exp

bp = Blueprint('danmaku', __name__, url_prefix='/api/danmaku')

def get_next_danmaku_id():
    """从counter数据库获取下一个弹幕ID"""
    result = mongo.db.counter.find_one_and_update(
        {"_id": "danmaku_id"},
        {"$inc": {"sequence_value": 1}},
        return_document=True,  # 返回更新后的文档
        upsert=True,  # 如果文档不存在则创建
        new=True  # 确保返回更新后的文档
    )
    return result["sequence_value"]
    

@bp.route('/send', methods=['POST'])
@login_required
def send_danmaku():
    """接受前端的弹幕存入数据库"""
    data = request.json
    aid = data.get('aid')
    content = data.get('content')
    color = data.get('color')
    danmaku_type = data.get('type')
    video_time = data.get('video_time')

    if len(content) > 40:
        return jsonify(state="error", message="弹幕内容不能超过40个字"), 400
    
    # 获取用户UID、当前时间戳和下一个弹幕ID
    uid = session['user']['uid']
    timestamp = time.time()
    danmaku_id = get_next_danmaku_id()

    # 更新数据库
    mongo.db.danmaku.update_one(
        {"aid": aid},
        {
            "$push": {
                "danmakus": {
                    "danmaku_id": danmaku_id,
                    "uid": uid,
                    "content": content,
                    "color": color,
                    "type": danmaku_type,
                    "video_time": video_time,
                    "timestamp": timestamp
                }
            }
        },
        upsert=True
    )
    mongo.db.video.update_one({"aid": aid},{"$inc": {"data.danmaku": 1}})
    adjust_points_and_exp(session['user']['uid'], -0.2, 0.2, reason=f"在视频aid:{aid}下发送弹幕")
    return jsonify(state="succeed", message="弹幕发送成功", danmaku_id=danmaku_id), 200


@bp.route('/<int:aid>', methods=['GET'])
def get_danmakus(aid):
    """获取指定视频的全部弹幕"""

    video_data = mongo.db.danmaku.find_one({"aid": aid})

    if video_data:
        danmakus = video_data.get('danmakus', [])

        danmakus_filtered = [{
            'danmaku_id': dm['danmaku_id'],
            'content': dm['content'],
            'video_time': dm['video_time'],
            'color': dm['color'],
            'type': dm['type']
        } for dm in danmakus]
    else:
        danmakus_filtered = []

    return jsonify(danmakus=danmakus_filtered), 200