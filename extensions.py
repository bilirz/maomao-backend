# 标准库导入
import logging
# 第三方库导入
from redis import Redis
from flask_pymongo import PyMongo
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from flask_cors import CORS
from flask_socketio import SocketIO

redis_client = Redis(host='localhost', port=6379, decode_responses=True)

mongo = PyMongo()

limiter = Limiter(
    key_func=get_remote_address
)

cors = CORS(supports_credentials=True)

socketio = SocketIO(cors_allowed_origins="*")


# def setup_logging(app):
#     logging.basicConfig(level=logging.DEBUG, filename="./app.log")
# setup_logging(app)
