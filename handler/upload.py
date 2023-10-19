# 标准库导入
import os
import time
from uuid import uuid4
from flask import Blueprint, request, jsonify, current_app, session
from werkzeug.utils import secure_filename
from redis.lock import Lock
import redis
# 应用/模块内部导入
from extensions import mongo, limiter
from cos import upload_to_cos

bp = Blueprint('upload', __name__, url_prefix='/api/upload')
r = redis.StrictRedis(host='localhost', port=6379, db=0)


def get_video_upload_folder():
    return os.path.join(current_app.root_path, current_app.config['VIDEO_UPLOAD_FOLDER'])


def get_cover_upload_folder():
    return os.path.join(current_app.root_path, current_app.config['COVER_UPLOAD_FOLDER '])


def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower()


def get_next_sequence_value(sequence_name):
    coll = mongo.db.counter
    sequence_document = coll.find_one_and_update(
        {'_id': sequence_name}, 
        {'$inc': {'sequence_value': 1}},
        upsert=True,
        return_document=True
    )
    
    if not sequence_document:
        coll.insert_one({'_id': sequence_name, 'sequence_value': 1})
        return 1
    else:
        return sequence_document["sequence_value"]


# 这里加了限制，60秒只能POST一个视频
@limiter.limit("1 per minute")
@bp.route('/video', methods=['POST'])
def upload_video_temporarily():
    if 'user' not in session:
        return jsonify(state='error', message='用户未登录'), 403

    video_upload_folder = get_video_upload_folder()

    if not os.path.exists(video_upload_folder):
        os.makedirs(video_upload_folder)

    if 'file' not in request.files:
        return jsonify(state='error', message='无文件'), 400

    file = request.files['file']
    if file.content_length > 100 * 1024 * 1024:  # 100MB
        return jsonify(state='error', message='视频太大，超过了100MB的限制'), 400

    if file and allowed_file(file.filename):
        unique_id = uuid4().hex
        filename = f"{unique_id}.mp4"
        filepath = os.path.join(video_upload_folder, filename)
        file.save(filepath)
        return jsonify(state='success', message='视频上传成功', filename=filename), 200
    else:
        return jsonify(state='error', message='文件类型不允许'), 400


# 这里也加了限制，同时使用锁锁住用户操作
@limiter.limit("1 per minute")
@bp.route('/submit', methods=['POST'])
def submit_form():
    client_ip = request.headers.get('CF-Connecting-IP') or request.headers.get('X-Forwarded-For') or request.remote_addr
    lock_name = f"submit_lock_{client_ip}"
    lock = Lock(r, lock_name, timeout=60)  # 锁定60秒

    if not lock.acquire(blocking=False):  
        return jsonify(state='error', message='来自该IP的请求过于频繁'), 429

    try:
        if 'user' not in session:
            return jsonify(state='error', message='用户未登录'), 403

        video_filename = request.form.get("video")
        cover_file = request.files.get('cover')

        if not video_filename or not cover_file:
            return jsonify(state='error', message='未提供视频或封面文件名'), 400
        
        if cover_file and cover_file.content_length > 5 * 1024 * 1024:
            return jsonify(state='error', message='封面大小超过5M，请重新上传'), 400

        video_upload_folder = get_video_upload_folder()
        cover_upload_folder = get_cover_upload_folder()

        video_path = os.path.join(video_upload_folder, video_filename)
        _, video_extension = os.path.splitext(video_filename)
        video_extension = video_extension[1:].lower()

        cover_filename = secure_filename(cover_file.filename)
        cover_path = os.path.join(cover_upload_folder, cover_filename)
        _, cover_extension = os.path.splitext(cover_filename)
        cover_extension = cover_extension[1:].lower()

        cover_file.save(cover_path)

        current_aid = get_next_sequence_value("video_aid")

        # 修改上传到 COS 的路径名
        cos_video_path = f"videos_original/{current_aid}.{video_extension}"
        upload_to_cos(video_path, cos_video_path)
        cos_cover_path = f"covers_original/{current_aid}.{cover_filename}"
        upload_to_cos(cover_path, cos_cover_path)

        tags = request.form.get("tags").split(',')
        if len(tags) != len(set(tags)):
            return "标签重复，请检查并重新提交", 400
        
        # 检查每个标签的长度
        for tag in tags:
            if len(tag) > 12:
                return "每个标签的长度不能超过12个字符！", 400

        # 检查标签总数
        if len(tags) > 12:
            return "最多只能有12个标签！", 400
        
        # 检查是否有重复标签
        if len(tags) != len(set(tags)):
            return "标签重复，请检查并重新提交", 400
        
        coll = mongo.db.video
        coll.insert_one({
          'aid': current_aid,
          'title': request.form.get("title"),
          'category': int(request.form.get("category")),
          'description': request.form.get("description"),
          'time': time.time(),
          'uid': session['user']['uid'],
          'tags': request.form.get("tags").split(','),
          'source': request.form.get("source"),
          'origin': request.form.get("origin"),
          'data': {
              'view': 0,
              'like': 0,
              'dislike': 0,
              'coin': 0,
              'share': 0,
              'favorite': 0,
              'danmaku': 0
          },
          "hidden": {
              "is_hidden": False,  # 默认不隐藏
              'reason': '',
              'grade': ''  # TODO: 视频封禁等级 1:仅隐藏，不删除视频 2:直接删除视频
          }
      })
    finally:
        lock.release()

    return jsonify(state='success', message='提交成功', aid=current_aid)