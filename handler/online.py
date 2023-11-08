# 标准库导入
import time
# 第三方库导入
from flask import Blueprint, jsonify
# 应用/模块内部导入
from extensions import mongo
from utils import get_real_ip

bp = Blueprint('online', __name__, url_prefix='/api/online')


@bp.route('/visited', methods=['POST'])
def visited():
    """接受前端的访问记录存入数据库"""
    current_hour_timestamp = int(time.time()) // 3600 * 3600

    visits_collection = mongo.db.visit
    visit = visits_collection.find_one(
        {'hour_timestamp': current_hour_timestamp})

    if visit:
        visits_collection.update_one(
            {'hour_timestamp': current_hour_timestamp}, {'$inc': {'count': 1}})
    else:
        visits_collection.insert_one(
            {'hour_timestamp': current_hour_timestamp, 'count': 1})

    return jsonify({'message': '访问已经统计'}), 200


@bp.route('/get_last_24h_visits', methods=['GET'])
def get_last_24h_visits():
    """获取过去24小时的访问记录"""
    current_hour_timestamp = int(time.time()) // 3600 * 3600
    last_24_hour_timestamps = [
        current_hour_timestamp - 3600*i for i in range(24)]

    visits_collection = mongo.db.visit
    visits = list(visits_collection.find(
        {'hour_timestamp': {'$in': last_24_hour_timestamps}}))

    data = {str(hour_timestamp)
                : 0 for hour_timestamp in last_24_hour_timestamps}

    for visit in visits:
        data[str(visit['hour_timestamp'])] = visit['count']

    return jsonify(data), 200
