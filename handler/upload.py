# 标准库导入
import os
import uuid
import time
import subprocess
# 第三方库导入
from flask import Blueprint, request, jsonify, current_app, session
from werkzeug.utils import secure_filename
from PIL import Image
import redis
from redis.lock import Lock
# 应用/模块内部导入
from extensions import mongo, limiter


bp = Blueprint('upload', __name__, url_prefix='/api/upload')
r = redis.StrictRedis(host='localhost', port=6379, db=0)

def get_temp_video_folder():
    return os.path.join(current_app.root_path, current_app.config['TEMP_VIDEO_FOLDER'])

def get_video_upload_folder():
    return os.path.join(current_app.root_path, current_app.config['VIDEO_UPLOAD_FOLDER'])

def get_temp_image_folder():
    return os.path.join(current_app.root_path, current_app.config['TEMP_IMAGE_FOLDER'])

def get_image_upload_folder():
    return os.path.join(current_app.root_path, current_app.config['IMAGE_UPLOAD_FOLDER'])

def allowed_video(filename):
    allowed_extensions = current_app.config['ALLOWED_EXTENSIONS']
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in allowed_extensions

def allowed_image(filename):
    allowed_extensions = current_app.config['ALLOWED_IMAGE_EXTENSIONS']
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in allowed_extensions

def save_temp_cover(file):
    temp_image_folder = get_temp_image_folder()
    if not os.path.exists(temp_image_folder):
        os.makedirs(temp_image_folder)

    if file and allowed_image(file.filename):
        filename = secure_filename(file.filename)
        filepath = os.path.join(temp_image_folder, filename)
        file.save(filepath)

        # 调整和压缩图像
        resized_output_path = os.path.join(temp_image_folder, "resized_" + filename)
        resize_and_compress_image(filepath, resized_output_path)

        return resized_output_path
    else:
        return None


def move_cover_to_final_path(temp_path, aid):
    image_upload_folder = get_image_upload_folder()
    if not os.path.exists(image_upload_folder):
        os.makedirs(image_upload_folder)

    final_path = os.path.join(image_upload_folder, f"{aid}.jpg")
    os.rename(temp_path, final_path)
    return final_path

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


# 压缩视频
def compress_video(input_path, output_path):
    cmd = [
        'ffmpeg',
        '-i', input_path,  # 输入视频路径
        '-vf', "scale='2*trunc((iw*480/ih)/2)':'480'",  # 保持高度为480，宽度自动调整并确保是2的倍数
        '-c:v', 'libx264',  # 使用H.264编码
        '-crf', '30',  # 设置压缩率。值越小，质量越好。通常在18到28之间
        '-preset', 'faster',  # 设置编码速度。可选值：ultrafast, superfast, veryfast, faster, fast, medium, slow, slower, veryslow
        '-c:a', 'aac',  # 使用AAC音频编码
        '-strict', 'experimental',
        '-b:a', '128k',  # 设置音频比特率
        output_path  # 输出视频路径
    ]
    subprocess.call(cmd)


# 压缩后视频转hls(m3u8)
def convert_to_hls(input_path, aid):
    hls_aid_folder = os.path.join(current_app.config['HLS_VIDEO_FOLDER'], str(aid))
    if not os.path.exists(hls_aid_folder):
        os.makedirs(hls_aid_folder)
        
    cmd = [
        'ffmpeg',
        '-i', input_path,
        '-profile:v', 'baseline',
        '-level', '3.0',
        '-start_number', '0',
        '-hls_time', '10',
        '-hls_list_size', '0',
        '-f', 'hls',
        os.path.join(hls_aid_folder, 'index.m3u8')
    ]
    subprocess.call(cmd)

def get_video_duration(video_path):
    cmd = ['ffmpeg', '-i', video_path, '-hide_banner', '-show_entries', 'format=duration', '-v', 'quiet', '-of', 'csv=p=0']
    result = subprocess.run(cmd, capture_output=True, text=True)
    duration = float(result.stdout.strip())
    return duration


# 获取视频时长 
# TODO: 根据时长上传视频
def get_video_duration(file_path):
    cmd = [
        'ffprobe',
        '-v', 'error',
        '-show_entries', 'format=duration',
        '-of', 'default=noprint_wrappers=1:nokey=1',
        file_path
    ]
    result = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    return float(result.stdout)


# 封面处理
def resize_and_compress_image(input_path, output_path, max_height=720):
    img = Image.open(input_path)

    # 如果图像的高度大于最大高度，则按比例缩放
    if img.height > max_height:
        scale_factor = max_height / img.height
        new_width = int(img.width * scale_factor)
        img = img.resize((new_width, max_height))

    # 根据高度计算宽度以满足16:9的比例
    new_width = img.height * 16 // 9
    # 拉伸图像到16:9的比例
    img_resized = img.resize((new_width, img.height))

    # 如果图片有透明度通道，转换为RGB
    if img_resized.mode == 'RGBA':
        img_resized = img_resized.convert('RGB')

    img_resized.save(output_path, 'JPEG', quality=50)


# 存储封面
def save_cover(file):
    image_upload_folder = get_image_upload_folder()
    if not os.path.exists(image_upload_folder):
        os.makedirs(image_upload_folder)
        
    if file and allowed_image(file.filename):
        filename = secure_filename(file.filename)
        filepath = os.path.join(image_upload_folder, filename)
        file.save(filepath)
        
        # 调整和压缩图像
        resized_output_path = os.path.join(image_upload_folder, "resized_" + filename)
        resize_and_compress_image(filepath, resized_output_path)
        
        return resized_output_path
    else:
        return None


# 这里加了限制，60秒只能POST一个视频
@limiter.limit("1 per minute")
@bp.route('/video', methods=['POST'])
def upload_video_temporarily():
    if 'user' not in session:
        return jsonify(state='error', message='用户未登录'), 403

    temp_video_folder = get_temp_video_folder()
    video_upload_folder = get_video_upload_folder()

    if not os.path.exists(temp_video_folder):
        os.makedirs(temp_video_folder)

    if 'file' not in request.files:
        return jsonify(state='error', message='无文件'), 400

    file = request.files['file']
    if file.content_length > 100 * 1024 * 1024:  # 100MB
        return jsonify(state='error', message='视频太大，超过了100MB的限制'), 400

    if file and allowed_video(file.filename):
        unique_id = uuid.uuid4().hex
        original_filename = f"{unique_id}_original.mp4"
        compressed_filename = f"{unique_id}.mp4"

        original_filepath = os.path.join(temp_video_folder, original_filename)
        compressed_filepath = os.path.join(temp_video_folder, compressed_filename)

        file.save(original_filepath)

        # 压缩视频
        compress_video(original_filepath, compressed_filepath)

        # 移动压缩后的视频到./videos
        final_video_path = os.path.join(video_upload_folder, compressed_filename)
        os.rename(compressed_filepath, final_video_path)

        # 删除原始未压缩的视频
        os.remove(original_filepath)

        return jsonify(state='success', message='视频上传并压缩成功', filename=compressed_filename), 200
    else:
        return jsonify(state='error', message='文件类型不允许'), 400


# 这里也加了限制，同时使用锁锁住用户操作
@limiter.limit("1 per minute")
@bp.route('/submit', methods=['POST'])
def submit_form():
    client_ip = request.headers.get('CF-Connecting-IP') or request.headers.get('X-Forwarded-For') or request.remote_addr
    lock_name = f"submit_lock_{client_ip}"
    lock = Lock(r, lock_name, timeout=60)  # 锁定60秒

    # 非阻塞模式下尝试获取锁
    if not lock.acquire(blocking=False):  
        return jsonify(state='error', message='来自该IP的请求过于频繁'), 429

    try:
        if 'user' not in session:
            return jsonify(state='error', message='用户未登录'), 403

        video_filename = request.form.get("video")
        cover_file = request.files['cover']

        video_upload_folder = get_video_upload_folder()
        hls_video_folder = current_app.config['HLS_VIDEO_FOLDER']

        if not video_filename:
            return jsonify(state='error', message='未提供视频文件名'), 400

        if request.form.get("title") == '' or request.form.get("category") == '':
            return jsonify(state='error', message='未提供必选项'), 400

        source_video_path = os.path.join(video_upload_folder, video_filename)
        if not os.path.exists(source_video_path):
            return jsonify(state='error', message='找不到视频文件'), 404

        current_aid = get_next_sequence_value("video_aid")
        hls_aid_folder = os.path.join(hls_video_folder, str(current_aid))
        hls_output_path = os.path.join(hls_aid_folder, 'index.m3u8')

        # 转换并移动到HLS文件夹
        convert_to_hls(source_video_path, current_aid)
        os.remove(source_video_path)  # 从./videos中删除MP4

        # Handling the cover image
        if cover_file:
            temp_cover_path = save_temp_cover(cover_file)
            if not temp_cover_path:
                return jsonify(state='error', message='封面保存失败'), 400
            
            final_cover_path = move_cover_to_final_path(temp_cover_path, current_aid)
        else:
            return jsonify(state='error', message='没有提供封面文件'), 400

        coll = mongo.db.video
        coll.insert_one({
            'aid': current_aid,
            'title': request.form.get("title"),
            'category': int(request.form.get("category")),
            'description': request.form.get("description"),
            'time': time.time(),
            'uid': session['user']['uid'],
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
