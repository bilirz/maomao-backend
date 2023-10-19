# 第三方库导入
from flask import Blueprint, jsonify, request
# 应用/模块内部导入
from extensions import mongo


bp = Blueprint('space', __name__, url_prefix='/api/space')


@bp.route('/videos/<int:uid>', methods=['GET'])
def get_videos_by_uid(uid):
    start = request.args.get('start', default=1, type=int)
    count = request.args.get('count', default=10, type=int)
    
    page_number = max((start - 1) // count, 0)
    skip_amount = page_number * count

    coll = mongo.db.video
    cursor = (coll.find({'uid': uid})
             .sort([("time", -1)])
             .skip(skip_amount)
             .limit(count + 1))

    videos = list(cursor)
    has_more = len(videos) > count
    videos = videos[:count]

    for video in videos:
        del video["_id"]
        
        user = mongo.db.user.find_one({"uid": video["uid"]})
        video["uploader_name"] = user.get("name") if user else "未知"
        
        if "hidden" in video and "uid" in video["hidden"]:
            operator = mongo.db.user.find_one({"uid": video["hidden"]["uid"]})
            video["hidden"]["operator_name"] = operator.get("name") if operator else "未知"
            video["hidden"].pop("uid", None)
        elif "hidden" in video:
            video["hidden"]["operator_name"] = "未知"

    return jsonify({"data": videos, "hasMore": has_more})


@bp.route('/<int:uid>', methods=['GET'])
def get_uid_info(uid):
    user_info = mongo.db.user.find_one({'uid': uid})

    if not user_info:
        return jsonify(state='error', message='用户名未找到'), 404


    data = {
        "name": user_info.get("name"),
        "registration_time": user_info.get("time"),
        "experience": user_info.get("checkin", {}).get("experience")
    }

    return jsonify(data)