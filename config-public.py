from datetime import timedelta

# 基础或全局配置
DEBUG = True
SECRET_KEY = ''
MAX_CONTENT_LENGTH = 100 * 1024 * 1024
PERMANENT_SESSION_LIFETIME = timedelta(days=30)

# 路径和文件夹配置
STATIC_FOLDER = './dist'
TEMPLATE_FOLDER = './dist'
VIDEO_UPLOAD_FOLDER = './videos'
COVER_UPLOAD_FOLDER = './covers'
FACE_UPLOAD_FOLDER = './faces'

# 数据库配置
MONGO_URI = 'mongodb://localhost:27017/mao'
RATELIMIT_STORAGE_URI = "redis://localhost:6379"

# 邮件配置
MAIL_SERVER = 'smtp.exmail.qq.com'
MAIL_PORT = 465
MAIL_USERNAME = ''
MAIL_PASSWORD = ''

# 第三方服务配置 - 腾讯云COS
COS_SECRET_ID = ''
COS_SECRET_KEY = ''
COS_ENDPOINT = ''
COS_BUCKET = ''
COS_PUBLIC_URL = ''