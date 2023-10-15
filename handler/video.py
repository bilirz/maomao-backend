# 标准库导入
import os
import math
from datetime import datetime, timedelta
# 第三方库导入
from flask import Blueprint, jsonify, send_from_directory, current_app, request, session
# 应用/模块内部导入
from extensions import mongo
from utils import login_required


bp = Blueprint('video', __name__, url_prefix='/api/video')

@bp.route('/list', methods=['GET'])
def get_videos():
    start = request.args.get('start', default=1, type=int)
    count = request.args.get('count', default=10, type=int)
    
    # 排序条件：根据时间从新到旧排序
    page_number = max((start - 1) // count, 0)  # 计算页数，确保页数至少为0
    skip_amount = page_number * count

    cursor = (mongo.db.video.find()
          .sort([("time", -1)])  # 按照发布时间从新到旧排序
          .skip(skip_amount)
          .limit(count + 1))
    
    videos = list(cursor)
    has_more = len(videos) > count
    videos = videos[:count]  # 只返回所请求的元素数量

    for video in videos:
        video.pop('_id', None)

        # 查询上传者的名称
        user = mongo.db.user.find_one({"uid": video["uid"]})
        video["uploader_name"] = user.get("name") if user else "Unknown"

        # 如果视频被隐藏，查询操作人的名称
        if "hidden" in video and "uid" in video["hidden"]:
            operator = mongo.db.user.find_one({"uid": video["hidden"]["uid"]})
            video["hidden"]["operator_name"] = operator.get("name") if operator else "Unknown"
            # 删除uid字段，只留下operator_name字段
            video["hidden"].pop("uid", None)
        elif "hidden" in video:
            video["hidden"]["operator_name"] = "Unknown"

    return jsonify({"data": videos, "hasMore": has_more})


@bp.route('/cover/<int:aid>', methods=['GET'])
def video_cover(aid):
    cover_filename = f"{aid}.jpg"
    cover_path = os.path.join(current_app.config['IMAGE_UPLOAD_FOLDER'], cover_filename)
    if not os.path.exists(cover_path):
        return jsonify({"message": "封面图片未找到"}), 404
    return send_from_directory(current_app.config['IMAGE_UPLOAD_FOLDER'], cover_filename)


@bp.route('/<int:aid>/index.m3u8', methods=['GET'])
def video_file(aid):
    video_filename = "index.m3u8"

    # 创建完整路径，例如：'./hls_videos/1/index.m3u8'
    video_path = os.path.join(current_app.config['HLS_VIDEO_FOLDER'], str(aid), video_filename)

    if not os.path.exists(video_path):
        return jsonify({"message": "视频文件未找到"}), 404

    # 从aid目录发送index.m3u8文件
    return send_from_directory(os.path.join(current_app.config['HLS_VIDEO_FOLDER'], str(aid)), video_filename, mimetype="application/vnd.apple.mpegurl")

@bp.route('/<int:aid>/<path:filename>', methods=['GET'])
def video_segment(aid, filename):
    # 创建完整路径，例如：'./hls_videos/1/somefile.ts'
    video_segment_path = os.path.join(current_app.config['HLS_VIDEO_FOLDER'], str(aid), filename)

    if not os.path.exists(video_segment_path):
        return jsonify({"message": "文件未找到"}), 404

    # 检查文件是否是.ts文件
    if filename.endswith('.ts'):
        mimetype = "video/MP2T"
    elif filename.endswith('.m3u8'):
        mimetype = "application/vnd.apple.mpegurl"
    else:
        mimetype = None  # Flask将自动设置MIME类型

    return send_from_directory(os.path.join(current_app.config['HLS_VIDEO_FOLDER'], str(aid)), filename, mimetype=mimetype)


@bp.route('/add/view/<int:aid>', methods=['POST'])
def add_view(aid):
    client_ip = request.headers.get("CF-Connecting-IP", request.remote_addr)
    ip_record = mongo.db.video_ip_view.find_one({"ip": client_ip})
    now = datetime.now().timestamp() # 获取当前时间戳
    thirty_minutes_ago = now - 30 * 60  # 30分钟前的时间戳

    # IP记录还不存在
    if not ip_record:
        mongo.db.video_ip_view.insert_one({"ip": client_ip, "views": {str(aid): now}})
        mongo.db.video.update_one({"aid": aid}, {"$inc": {"data.view": 1}})
        return jsonify({"message": "播放量增加成功"})
    else:
        last_viewed = ip_record["views"].get(str(aid), None)
        if last_viewed:
            # 将datetime对象转换为时间戳
            last_viewed_timestamp = last_viewed.timestamp()
        if not last_viewed or last_viewed_timestamp < thirty_minutes_ago:
            ip_record["views"][str(aid)] = now
            mongo.db.video_ip_view.update_one({"ip": client_ip}, {"$set": {"views": ip_record["views"]}})
            mongo.db.video.update_one({"aid": aid}, {"$inc": {"data.view": 1}})
            return jsonify({"message": "播放量增加成功"})
        else:
            return jsonify({"message": "播放量增加失败(30)"})
    

@bp.route('/get/<int:aid>', methods=['GET'])
def get_video_info(aid):
    # 查询指定aid的视频信息
    video = mongo.db.video.find_one({"aid": aid})
    if not video:
        return jsonify({"message": "Video not found"}), 404
    # 如果不想在输出中显示MongoDB的_id字段
    video.pop('_id', None)
    return jsonify(video)


@bp.route('/toggle/like/<int:aid>', methods=['POST'])
@login_required
def toggle_like_video(aid):
    uid = session['user']['uid']
    user_record = mongo.db.video_like.find_one({"uid": uid})

    # 用户记录还不存在
    if not user_record:
        mongo.db.video_like.insert_one({"uid": uid, "liked_videos": [aid]})
        mongo.db.video.update_one({"aid": aid}, {"$inc": {"data.like": 1}})
        return jsonify({"message": "点赞成功", "likes": 1})
    else:
        # 用户已点赞
        if aid in user_record["liked_videos"]:
            user_record["liked_videos"].remove(aid)
            mongo.db.video_like.update_one({"uid": uid}, {"$set": {"liked_videos": user_record["liked_videos"]}})
            mongo.db.video.update_one({"aid": aid}, {"$inc": {"data.like": -1}})
            return jsonify({"message": "取消点赞成功", "likes": -1})
        # 用户还未点赞
        else:
            user_record["liked_videos"].append(aid)
            mongo.db.video_like.update_one({"uid": uid}, {"$set": {"liked_videos": user_record["liked_videos"]}})
            mongo.db.video.update_one({"aid": aid}, {"$inc": {"data.like": 1}})
            return jsonify({"message": "点赞成功", "likes": 1})


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


@bp.route('/comment/<int:aid>', methods=['POST'])
@login_required
def post_comment(aid):
    uid = session['user']['uid']
    content = request.json.get('content')

    # 数据验证
    if not content:
        return jsonify({"message": "内容不能为空"}), 400

    if len(content) > 200:
        return jsonify({"message": "评论长度不能超过200字"}), 400
    print(is_on_cool_down(uid, content))
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
        "floor": new_floor  # 添加这一行来记录楼层号
    }

    # 在插入评论后，更新视频的最后一个评论楼层号
    mongo.db.comment.insert_one(comment)
    mongo.db.video.update_one({"aid": aid}, {"$set": {"last_comment_floor": new_floor}})
    mongo.db.comment_cool_down.update_one(
        {"uid": uid},
        {"$set": {"time": datetime.now().timestamp(), "content": content}},
        upsert=True  # 如果不存在则插入新记录
    )

    return jsonify({"message": "评论发布成功"})


@bp.route('/reply/<ObjectId:comment_id>', methods=['POST'])
@login_required
def post_reply(comment_id):
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
        "floor": new_floor  # 使用新的楼层号
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

@bp.route('/comments/<int:aid>', methods=['GET'])
def get_comments(aid):
    cursor = mongo.db.comment.find({"aid": aid}).sort("time", -1)  # 先按时间降序排序
    comments = list(cursor)

    total_floor = len(comments) # 获取评论的总数
    for index, comment in enumerate(comments):
        comment["_id"] = str(comment["_id"])
        user = mongo.db.user.find_one({"uid": comment["uid"]})
        comment["username"] = user["name"] if user else "Unknown"
        for reply in comment['replies']:
            reply_user = mongo.db.user.find_one({"uid": reply["uid"]})
            reply['username'] = reply_user['name'] if reply_user else "Unknown"
        comment["floor"] = total_floor - index  # 逆向分配楼层号

    return jsonify(comments)

from datetime import datetime
import math
from flask import jsonify, request


@bp.route('/hot-list', methods=['GET'])
def get_hot_videos():
    start = int(request.args.get('start', 1)) - 1  # 转换为基于0的索引
    count = int(request.args.get('count', 10))
    now = datetime.now()
    videos_cursor = mongo.db.video.find()
    comments_cursor = mongo.db.comment.aggregate([
        {"$group": {"_id": "$aid", "total_comments": {"$sum": 1}}}
    ])

    # 创建评论计数映射
    comments_map = {item["_id"]: item["total_comments"] for item in comments_cursor}

    video_scores = []

    for video in videos_cursor:
        aid = video["aid"]
        video_date = datetime.utcfromtimestamp(video["time"])
        days_since_release = (now - video_date).days
        # 应用对数衰减来避免给新视频过多的权重
        time_decay_factor = 1 / (1 + math.log(1 + days_since_release))
        
        score = (
            video["data"]["view"] * 0.5 +  
            video["data"]["like"] * 10 + 
            comments_map.get(aid, 0) * 2 +
            time_decay_factor  # 时间衰减因子
        )
        video_scores.append((video, score))

    # 按分数排序
    video_scores.sort(key=lambda x: x[1], reverse=True)

    # TOP20
    end = start + count
    paged_video_objects = [video[0] for video in video_scores[start:end]]

    formatted_videos = []
    for video in paged_video_objects:
        video.pop('_id', None)
        
        user = mongo.db.user.find_one({"uid": video["uid"]})
        video["uploader_name"] = user.get("name") if user else "Unknown"

        # 如果视频被隐藏，查询操作人的名称
        if "hidden" in video and "uid" in video["hidden"]:
            operator = mongo.db.user.find_one({"uid": video["hidden"]["uid"]})
            video["hidden"]["operator_name"] = operator.get("name") if operator else "Unknown"
            # 删除uid字段，只留下operator_name字段
            video["hidden"].pop("uid", None)
        elif "hidden" in video:
            video["hidden"]["operator_name"] = "Unknown"

        formatted_videos.append(video)

    has_more = len(video_scores) > end

    return jsonify({"data": formatted_videos, "hasMore": has_more})