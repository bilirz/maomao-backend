# 标准库导入
from datetime import datetime
# 第三方库导入
from flask import Blueprint, jsonify, request, session
# 应用/模块内部导入
from extensions import mongo
from utils import login_required, adjust_points_and_exp


bp = Blueprint('comment', __name__, url_prefix='/api/comment')

ALLOWED_PAGE_TYPES = ["video", "index", "log"]

def is_on_cool_down(uid, content):
    # 根据uid查找该用户的最后一次评论
    last_comment = mongo.db.comment_cool_down.find_one({"uid": uid})
    
    # 如果用户没有评论记录或者已经过了冷却时间，则可以评论
    if not last_comment:
        return False
    else:
        if (datetime.now().timestamp() - last_comment['time']) >= 3:
            return False
        elif last_comment['content'] == content:
            return True
        else:
            return True


@bp.route('/<string:page_type>', defaults={'aid': None}, methods=['POST'])
@bp.route('/<string:page_type>/<int:aid>', methods=['POST'])
@login_required
def post_comment(page_type, aid):
    if page_type not in ALLOWED_PAGE_TYPES:
        return jsonify({"message": "Invalid URL"}), 400
    uid = session['user']['uid']
    content = request.json.get('content')

    # 数据验证
    if not content:
        return jsonify({"message": "内容不能为空"}), 400

    if len(content) > 200:
        return jsonify({"message": "评论长度不能超过200字"}), 400
    if is_on_cool_down(uid, content):
        return jsonify({"message": "请等待3秒后再评论或确保内容不与上一次相同"}), 400

    # 获取视频的最后一个评论楼层号
    video = mongo.db.video.find_one({"aid": aid})
    last_comment_floor = video.get("last_comment_floor", 0) if video else 0
    new_floor = last_comment_floor + 1

    comment = {
        "aid": aid,
        "uid": uid,
        "content": content,
        "time": datetime.now().timestamp(),
        "parent_id": None,
        "replies": [],
        "floor": new_floor,  # 添加这一行来记录楼层号
        "page_type": page_type
    }

    # 在插入评论后，更新视频的最后一个评论楼层号
    mongo.db.comment.insert_one(comment)
    mongo.db.video.update_one({"aid": aid}, {"$set": {"last_comment_floor": new_floor}})
    mongo.db.comment_cool_down.update_one(
        {"uid": uid},
        {"$set": {"time": datetime.now().timestamp(), "content": content}},
        upsert=True  # 如果不存在则插入新记录
    )

    if aid is None:
        adjust_points_and_exp(uid, -0.2, 0.2, reason=f"在{page_type}页面发布评论")
    else:
        adjust_points_and_exp(uid, -0.2, 0.2, reason=f"在视频aid:{aid}下发布评论")
        

    return jsonify({"message": "评论发布成功"})


@bp.route('/<string:page_type>/reply/<ObjectId:comment_id>', methods=['POST'])
@login_required
def post_reply(page_type, comment_id):
    if page_type not in ALLOWED_PAGE_TYPES:
        return jsonify({"message": "Invalid URL"}), 400
    uid = session['user']['uid']
    content = request.json.get('content')
    parent_reply_id = request.json.get('parent_reply_id', None)

    # 数据验证
    if not content:
        return jsonify({"message": "内容不能为空"}), 400

    if len(content) > 100:
        return jsonify({"message": "回复长度不能超过100字"}), 400

    if is_on_cool_down(uid, content):
        return jsonify({"message": "请等待3秒后再回复或确保内容不与上一次相同"}), 400

    # 获取评论的最后一个回复楼层号
    main_comment = mongo.db.comment.find_one({"_id": comment_id})
    last_reply_floor = main_comment.get("last_reply_floor", 0) if main_comment else 0
    new_floor = last_reply_floor + 1

    reply = {
        "uid": uid,
        "content": content,
        "time": datetime.now().timestamp(),
        "parent_reply_id": parent_reply_id,
        "floor": new_floor,  # 使用新的楼层号
        "page_type": page_type
    }

    # 在插入回复后，更新主评论的最后一个回复楼层号
    mongo.db.comment.update_one({"_id": comment_id}, {
        "$push": {"replies": reply},
        "$set": {"last_reply_floor": new_floor}
    })

    mongo.db.comment_cool_down.update_one(
        {"uid": uid},
        {"$set": {"time": datetime.now().timestamp(), "content": content}},
        upsert=True  # 如果不存在则插入新记录
    )

    return jsonify({"message": "回复成功"})


@bp.route('/<string:page_type>', defaults={'aid': None}, methods=['GET'])
@bp.route('/<string:page_type>/<int:aid>', methods=['GET'])
def get_comments(page_type, aid):
    print(aid)
    if page_type not in ALLOWED_PAGE_TYPES:
        return jsonify({"message": "Invalid URL"}), 400

    # 检索与给定类型和aid匹配的评论
    filter_criteria = {"page_type": page_type}
    if aid is not None:
        filter_criteria["aid"] = aid

    cursor = mongo.db.comment.find(filter_criteria).sort("time", -1)
    comments = list(cursor)

    total_floor = len(comments) # 获取评论的总数
    for index, comment in enumerate(comments):
        comment["_id"] = str(comment["_id"])
        user = mongo.db.user.find_one({"uid": comment["uid"]})
        comment["username"] = user["name"] if user else "未知"
        for reply in comment['replies']:
            reply_user = mongo.db.user.find_one({"uid": reply["uid"]})
            reply['username'] = reply_user['name'] if reply_user else "未知"
        comment["floor"] = total_floor - index  # 逆向分配楼层号

    return jsonify(comments)