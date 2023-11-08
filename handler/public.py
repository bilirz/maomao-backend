# 第三方库导入
import requests
from flask import request, Blueprint, make_response, current_app


bp = Blueprint('public', __name__, url_prefix='/api/public')


@bp.route('/cos/<path:subpath>', methods=['GET', 'POST', 'PUT', 'DELETE'])
def proxy(subpath):
    """代理COS资源"""
    method = request.method
    data = request.get_data()

    resp = requests.request(
        method=method,
        url=f"{current_app.config['COS_PUBLIC_URL']}/{subpath}",
        headers={key: value for (key, value)
                 in request.headers if key != 'Host'},
        data=data,
        cookies=request.cookies,
        allow_redirects=False  # 让Flask处理重定向
    )

    response = make_response(resp.content, resp.status_code)
    for key, value in resp.headers.items():
        # 排除Transfer-Encoding和Connection头部，因为会报错
        if key.lower() not in ['transfer-encoding', 'connection']:
            response.headers[key] = value

    return response
