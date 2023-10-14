# 基础或全局配置
DEBUG = True
SEND_FILE_MAX_AGE_DEFAULT = 0
SECRET_KEY = ''
MAX_CONTENT_LENGTH = 100 * 1024 * 1024

# 路径和文件夹配置
STATIC_FOLDER = './dist'
TEMPLATE_FOLDER = './dist'
VIDEO_UPLOAD_FOLDER = './videos'
TEMP_VIDEO_FOLDER = './temp-videos'
IMAGE_UPLOAD_FOLDER = './images'
TEMP_IMAGE_FOLDER = './temp-images'
HLS_VIDEO_FOLDER = './hls_videos'

# 第三方服务配置
RATELIMIT_STORAGE_URI = "redis://localhost:6379"
MONGO_URI = 'mongodb://localhost:27017/mao'
MAIL_SERVER = 'smtp.exmail.qq.com'
MAIL_PORT = 465
MAIL_USERNAME = ''
MAIL_PASSWORD = ''

# 与应用功能或业务相关的配置
ALLOWED_EXTENSIONS = {'mp4', 'avi', 'mov'}
ALLOWED_IMAGE_EXTENSIONS = {'jpeg', 'jpg', 'png'}
