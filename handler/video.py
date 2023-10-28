# 标准库导入
import os
import math
from datetime import datetime
# 第三方库导入
from flask import Blueprint, jsonify, request, session
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
        video["uploader_name"] = user.get("name") if user else "未知"

        # 如果视频被隐藏，查询操作人的名称
        if "hidden" in video and "uid" in video["hidden"]:
            operator = mongo.db.user.find_one({"uid": video["hidden"]["uid"]})
            video["hidden"]["operator_name"] = operator.get("name") if operator else "未知"
            # 删除uid字段，只留下operator_name字段
            video["hidden"].pop("uid", None)
        elif "hidden" in video:
            video["hidden"]["operator_name"] = "未知"

    return jsonify({"data": videos, "hasMore": has_more})


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
        if not last_viewed or last_viewed < thirty_minutes_ago:
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
        return jsonify({"message": "无法找到视频"}), 404
    
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

    SMOOTHING = 10

    for video in videos_cursor:
        aid = video["aid"]
        views = video["data"]["view"]
        print()

        # 排除播放量小于10的视频
        if views < 10:
            continue

        video_date = datetime.utcfromtimestamp(video["time"])
        days_since_release = (now - video_date).days
        time_decay_factor = 1 / (1 + math.log(1 + days_since_release))

        likes = video["data"]["like"]
        comments = comments_map.get(aid, 0)

        like_view_ratio = (likes + SMOOTHING) / (views + SMOOTHING)
        comment_view_ratio = (comments + SMOOTHING) / (views + SMOOTHING)

        score = (
            views * 3 + 
            likes * 6 + 
            comments * 1.5 +
            like_view_ratio * 50 +  
            comment_view_ratio * 40 + 
            time_decay_factor
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
        video["uploader_name"] = user.get("name") if user else "未知"

        # 如果视频被隐藏，查询操作人的名称
        if "hidden" in video and "uid" in video["hidden"]:
            operator = mongo.db.user.find_one({"uid": video["hidden"]["uid"]})
            video["hidden"]["operator_name"] = operator.get("name") if operator else "未知"
            # 删除uid字段，只留下operator_name字段
            video["hidden"].pop("uid", None)
        elif "hidden" in video:
            video["hidden"]["operator_name"] = "未知"

        formatted_videos.append(video)

    has_more = len(video_scores) > end

    return jsonify({"data": formatted_videos, "hasMore": has_more})
