# 标准库导入
import time
import random
import os
from datetime import datetime, timedelta
from email.mime.text import MIMEText
from email.header import Header
# 第三方库导入
import bcrypt
import smtplib
from flask import Blueprint, request, session, jsonify, current_app
import redis
from redis.lock import Lock
from werkzeug.utils import secure_filename
# 应用/模块内部导入
from extensions import mongo, limiter
from utils import login_required
from cos import upload_to_cos

bp = Blueprint('user', __name__, url_prefix='/api/user')
r = redis.StrictRedis(host='localhost', port=6379, db=0)


# bcrypt加密
def bcrypt_hash(password):
    salt = bcrypt.gensalt()
    hashed = bcrypt.hashpw(password.encode('utf-8'), salt)
    return hashed.decode('utf-8'), salt.decode('utf-8')

def bcrypt_check(password, hashed_password):
    return bcrypt.checkpw(password.encode('utf-8'), hashed_password.encode('utf-8'))


@bp.route('/signin', methods=['POST'])
def signin():
    coll = mongo.db.user
    request_json = request.get_json()
    user = coll.find_one({'email':request_json['email']})
    if user is not None:
        if bcrypt_check(str(request_json['password']), user['password']):
            session['user'] = {
                'uid': user['uid'],
                'signin': True,
            }
            return jsonify(state='succeed', message='登录成功')
        else:
            return jsonify(state='error', message='密码错误')
    else:
        return jsonify(state='error', message='用户不存在')


@bp.route('/signup', methods=['POST'])
def signup():
    client_ip = request.headers.get('CF-Connecting-IP') or request.headers.get('X-Forwarded-For') or request.remote_addr
    lock_name = f"signup_lock_{client_ip}"
    lock = Lock(r, lock_name, timeout=300)  # 锁定300秒，限制每个IP每5分钟只能注册一次

    # 非阻塞模式下尝试获取锁
    if not lock.acquire(blocking=False):  
        return jsonify(state='error', message='来自该IP的请求过于频繁，请5分钟后再试'), 429

    try:
        coll = mongo.db.user
        request_json = request.get_json()

        user_name_length = len(request_json['name'])
        if user_name_length < 3 or user_name_length > 10:
            return jsonify(state='error', message='名字长度需要在3-10之间')

        if coll.find_one({'email': request_json['email']}) is None:
            if coll.find_one() is None:
                uid = 1
            else:
                uid = coll.find_one(sort=[('_id', -1)])['uid'] + 1
            hashed_password, salt = bcrypt_hash(str(request_json['password']))
            document = {
                'uid': uid,
                'email': request_json['email'],
                'name': request_json['name'],
                'password': hashed_password,
                'salt': salt,
                'time': time.time(),
                'status': 0,
            }
            coll.insert_one(document)
            return jsonify(state='succeed', message='注册成功')
        else:
            return jsonify(state='error', message='电子邮件已存在')
    finally:
        lock.release()


@limiter.limit("1 per minute")
@bp.route('/signup/auth', methods=['POST'])
def signup_auth():
    auth = ''.join([str(random.randint(0, 9)) for _ in range(6)])
    
    request_json = request.get_json()
    
    smtp = smtplib.SMTP_SSL(current_app.config['MAIL_SERVER'], current_app.config['MAIL_PORT'])
    smtp.login(user=current_app.config['MAIL_USERNAME'], password=current_app.config['MAIL_PASSWORD'])
    # TODO: 这里或许可以优化
    mail_msg = f'''
    <div style="border:3px solid #25ACE3; border-radius: 7px; margin: 10px; padding: 20px;">
    <div style="text-align: center;">
        <span style="font-size: 24px; font-weight: bold; background: #68ADEE">欢迎来到猫猫站！</span>
    </div>
    <br><br>
    <span style="color: #555;">您正在注册<a href="www.v.bilirz.com" style="color: #555;">猫猫站</a>新账号，验证代码是：<span style="font-weight: bold; color: #666">{auth}</span>，有效期为<span style="font-weight: bold; color: #666">5分钟</span>，请妥善保管。</span>
    <br>
    <span style="color: #555;">如果这不是您的行为，可直接删除这封邮件。</span>
    <br><br>
    <span style='font-size:5px color: #666;'>谢谢！</span>
    <br>
    <span style='font-size:5px color: #666;'>@认真猫</span>
    </div>
    <div style="text-align: center;">
        <span style='text-align: center; font-size:2px color: #666;'>BiliRZ 2023 ©All Rights Reserves</span>
    </div>
    '''
    message = MIMEText(mail_msg, 'html', 'utf-8')
    message['From'] = current_app.config['MAIL_USERNAME']
    message['To'] = request_json['email']
    message['Subject'] = Header(f'猫猫站 - 点击查看验证码', 'utf-8')

    smtp.sendmail(from_addr=current_app.config['MAIL_USERNAME'], to_addrs=request_json['email'], msg=message.as_string())
    
    document = {
        'email': request_json['email'],
        'auth': auth,
        'time': time.time(),
    }

    mongo.db.user_auth.replace_one({'email': request_json['email']}, document, upsert=True)

    return jsonify(state='succeed', message='验证邮件已发送')


@bp.route('/checkin', methods=['POST'])
@login_required
def checkin():
    # 获取当前用户
    uid = session['user']['uid']
    user = mongo.db.user.find_one({"uid": uid})
    
    if not user:
        return jsonify(state='error', message='用户不存在')

    # 获取上次签到时间
    last_checkin_timestamp = user["checkin"].get('last_checkin') if "checkin" in user else None
    last_checkin = datetime.fromtimestamp(last_checkin_timestamp) if last_checkin_timestamp else None

    # 判断是否可以签到
    now = datetime.now()
    if last_checkin and now - last_checkin < timedelta(hours=8):
        return jsonify(state='error', message='还未到签到时间，每8小时可签到一次。')

    # 更新签到时间、经验和积分
    mongo.db.user.update_one(
        {"uid": uid},
        {
            "$set": {"checkin.last_checkin": now.timestamp()},  # 使用时间戳
            "$inc": {"checkin.experience": 10, "checkin.points": 10}
        }
    )

    return jsonify(state='success', message='签到成功，+10经验，+10积分')


@bp.route('/session/get', methods=['GET'])
def getSession():
    coll = mongo.db.user
    if 'user' in session:
        user = coll.find_one({"uid": session['user']['uid']})

        # 检查并初始化checkin字段
        if "checkin" not in user:
            user["checkin"] = {
                'last_checkin': None,
                'experience': 0,
                'points': 0
            }
            coll.update_one({"uid": session['user']['uid']}, {"$set": {"checkin": user["checkin"]}})

        last_checkin_timestamp = user["checkin"].get('last_checkin') if "checkin" in user else None
        now_timestamp = datetime.now().timestamp()

        can_checkin = not last_checkin_timestamp or now_timestamp - last_checkin_timestamp >= 8 * 3600  # 8 hours in seconds
        
        return jsonify({
            **session['user'],
            'name': user['name'],
            'email': user['email'],
            'status': user['status'],
            'checkin':{
              'can_checkin': can_checkin,
              'last_checkin': last_checkin_timestamp,  # 直接返回时间戳
              'experience': user["checkin"].get('experience', 0),
              'points': user["checkin"].get('points', 0)
            }
        })
    else:
        return jsonify({'signin': False, 'status': 0, 'state': 'no_session'})
    

@bp.route('/signout', methods=['POST'])
def signout():
    session.clear()
    return jsonify(state='succeed', message='成功登出')


@bp.route('/update', methods=['POST'])
@login_required
def update_profile():
    coll = mongo.db.user
    new_name = request.form.get('name')
    cover_file = request.files.get('cover')

    if not new_name:
        return jsonify(state='error', message='名字为必填项'), 400

    uid = session['user'].get('uid')
    error_message = None

    if cover_file:
        if cover_file.content_length > 5 * 1024 * 1024:
            return jsonify(state='error', message='封面大小超过5M，请重新上传'), 400
        
        filename = f"{uid}.jpg"
        temp_path = os.path.join(current_app.config['FACE_UPLOAD_FOLDER'], filename)
        cover_file.save(temp_path)

        cos_file_path = f"face_original/{filename}"
        error_message = upload_to_cos(temp_path, cos_file_path)

        os.remove(temp_path)

    # 只有当上传没有错误时才更新数据库
    if not error_message:
        coll.update_one({"uid": uid}, {"$set": {"name": new_name}})
    else:
        return jsonify(state='error', message=error_message), 500

    return jsonify(state='succeed', message='名字修改成功'), 200