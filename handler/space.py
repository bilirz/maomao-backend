# 第三方库导入
from flask import Blueprint, jsonify, request, session
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
        "experience": user_info.get("checkin", {}).get("experience"),
        "followers_count": len(user_info.get("followers", [])),
        "following_count": len(user_info.get("following", []))
    }

    return jsonify(data)


@bp.route('/follow/<int:target_uid>', methods=['POST'])
def follow_user(target_uid):  # target_uid 表示想关注或取消关注的用户
    current_uid = session['user']['uid']

    if current_uid == target_uid:
        return jsonify(state='error', message='不能关注自己')
    
    coll = mongo.db.user
    target_user = coll.find_one({"uid": target_uid})

    if not target_user:
        return jsonify(state='error', message='用户名不存在'), 404

    current_user = coll.find_one({"uid": current_uid})

    # 如果用户已经关注了这个UP主，则取消关注
    if target_uid in current_user.get("following", []):
        coll.update_one({"uid": current_uid}, {"$pull": {"following": target_uid}})
        coll.update_one({"uid": target_uid}, {"$pull": {"followers": current_uid}})
        return jsonify(state='succeed', message='取消关注成功')

    # 否则，添加到关注列表中
    coll.update_one({"uid": current_uid}, {"$push": {"following": target_uid}})
    coll.update_one({"uid": target_uid}, {"$push": {"followers": current_uid}})
    return jsonify(state='succeed', message='关注成功')
    

@bp.route('/is_following/<int:target_uid>', methods=['GET'])
def is_following(target_uid):
    current_uid = session['user']['uid']

    if not current_uid:
        return jsonify(state='error', message='用户未登录'), 401

    coll = mongo.db.user

    current_user = coll.find_one({"uid": current_uid})

    if not current_user:
        return jsonify(state='error', message='当前用户不存在'), 404

    if target_uid in current_user.get("following", []):
        return jsonify(state='succeed', isFollowing=True, message='当前用户已关注目标用户')

    return jsonify(state='succeed', isFollowing=False, message='当前用户未关注目标用户')