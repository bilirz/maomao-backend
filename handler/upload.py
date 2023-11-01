# 标准库导入
import os
import time
from functools import wraps
# 第三方库导入
from uuid import uuid4
from flask import Blueprint, request, jsonify, current_app, session
from werkzeug.utils import secure_filename
from redis.lock import Lock
import redis
# 应用/模块内部导入
from extensions import mongo, limiter
from utils import login_required, adjust_points_and_exp
from cos import upload_to_cos

bp = Blueprint('upload', __name__, url_prefix='/api/upload')
r = redis.StrictRedis(host='localhost', port=6379, db=0)


def get_video_upload_folder():
    return os.path.join(current_app.root_path, current_app.config['VIDEO_UPLOAD_FOLDER'])


def get_cover_upload_folder():
    return os.path.join(current_app.root_path, current_app.config['COVER_UPLOAD_FOLDER'])


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


# def retry(exception_to_check, tries=3, delay=2, backoff=2):
#     """
#     重试装饰
#     exception_to_check: 异常检查
#     tries: 最大尝试次数
#     delay: 初始重试时延，单位为秒
#     backoff: 后退乘数，例如，值为2将使每次重试的延迟加倍
#     """
#     def deco_retry(func):
#         @wraps(func)
#         def f_retry(*args, **kwargs):
#             mtries, mdelay = tries, delay
#             while mtries > 1:
#                 try:
#                     return func(*args, **kwargs)
#                 except exception_to_check as e:
#                     print(f"{str(e)},  {mdelay} 秒后重试...")
#                     time.sleep(mdelay)
#                     mtries -= 1
#                     mdelay *= backoff
#             return func(*args, **kwargs)
#         return f_retry
#     return deco_retry


# 这里加了限制，60秒只能POST一个视频
@limiter.limit("1 per minute")
@login_required
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
@login_required
@bp.route('/submit', methods=['POST'])
def submit_form():
    client_ip = request.headers.get('CF-Connecting-IP') or request.headers.get('X-Forwarded-For') or request.remote_addr
    lock_name = f"submit_lock_{client_ip}"
    lock = Lock(r, lock_name, timeout=60)  # 锁定60秒
    
    forbidden_tags = ["自制", "转载", "游戏", "生活", "知识", "科技", "音乐", "鬼畜", "动画", "时尚", "舞蹈", "娱乐", "美食", "动物"]

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



        unique_id = request.form.get("unique_id")  # 获取合并后的文件的唯一ID
        if not unique_id:
            return jsonify(state='error', message='未提供合并后的视频文件ID'), 400
        
        video_path = os.path.join(video_upload_folder, f"{unique_id}.mp4")
        video_extension = "mp4"  # 合并后的文件是MP4格式

        cover_filename = secure_filename(cover_file.filename)
        cover_path = os.path.join(cover_upload_folder, cover_filename)
        _, cover_extension = os.path.splitext(cover_filename)
        cover_extension = cover_extension[1:].lower()

        cover_file.save(cover_path)

        current_aid = get_next_sequence_value("video_aid")

        # 修改上传到 COS 的路径名
        cos_video_path = f"videos_original/{current_aid}.{video_extension}"
        cos_cover_path = f"covers_original/{current_aid}.jpg"

        upload_to_cos(video_path, cos_video_path)

        upload_to_cos(cover_path, cos_cover_path)

        tags = request.form.get("tags").split(',')
        if len(tags) != len(set(tags)):
            return "标签重复，请检查并重新提交", 400
        
        # 检查每个标签的长度
        for tag in tags:
            if len(tag) > 12:
                return "每个标签的长度不能超过12个字符！", 400
            if tag in forbidden_tags:
                return jsonify(state='error', message=f'标签"{tag}"是被禁止的，请移除后再提交'), 400

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
        adjust_points_and_exp(session['user']['uid'], -1, 1, reason=f"发布{current_aid}视频")
    finally:
        lock.release()

    return jsonify(state='success', message='提交成功', aid=current_aid)


@bp.route('/video/chunk', methods=['POST'])
@login_required
def upload_video_chunk():
    if 'file' not in request.files:
        return jsonify(state='error', message='无文件'), 400

    chunk = request.files['file']
    unique_id = request.form.get('unique_id')
    chunk_index = int(request.form.get('index', 0))
    
    video_upload_folder = get_video_upload_folder()

    if not os.path.exists(video_upload_folder):
        os.makedirs(video_upload_folder)

    chunk_filename = f"{unique_id}_chunk_{chunk_index}.part"
    chunk_path = os.path.join(video_upload_folder, chunk_filename)
    chunk.save(chunk_path)


    coll = mongo.db.video_chunk
    coll.insert_one({
        'chunk_filename': chunk_filename,
        'index': chunk_index,
        'unique_id': unique_id,
        'uploaded_at': time.time(),
        'uid': session['user']['uid']
    })

    return jsonify(state='success', message='分片上传成功', chunk_filename=chunk_filename)


@bp.route('/video/merge', methods=['POST'])
@login_required
def merge_video_chunk():
    unique_id = request.json.get('unique_id')
    total_chunks = int(request.json.get('total', 0))

    video_upload_folder = get_video_upload_folder()
    merged_video_path = os.path.join(video_upload_folder, f"{unique_id}.mp4")

    # 为了效率，预先生成所有要合并的分片的文件路径
    chunk_paths = []
    for i in range(total_chunks):
        chunk_info = mongo.db.video_chunk.find_one({'unique_id': unique_id, 'index': i})
        if not chunk_info:
            return jsonify(state='error', message=f'分片 {i} 丢失'), 500
        chunk_paths.append(os.path.join(video_upload_folder, chunk_info['chunk_filename']))

    # 使用with语句确保文件描述符在完成后关闭
    with open(merged_video_path, 'wb') as merged_file:
        for chunk_path in chunk_paths:
            with open(chunk_path, 'rb') as chunk_file:
                merged_file.write(chunk_file.read())
            os.remove(chunk_path)  # 确保删除每个已合并的分片

    # 删除与此 unique_id 相关的所有分片记录
    mongo.db.video_chunk.delete_many({'unique_id': unique_id})

    return jsonify(state='success', message='视频合并成功', filename=f"{unique_id}.mp4")