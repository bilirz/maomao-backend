# 标准库导入
import logging
# 第三方库导入
from flask_pymongo import PyMongo
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from flask_cors import CORS


mongo = PyMongo()

limiter = Limiter(
    key_func=get_remote_address
)

cors = CORS(supports_credentials=True)


# def setup_logging(app):
#     logging.basicConfig(level=logging.DEBUG, filename="./app.log")
# setup_logging(app)
