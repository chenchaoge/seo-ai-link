"""
DataForSEO 官方示例客户端（照搬官方 Python 示例，加了请求超时）
"""

from base64 import b64encode
from http.client import HTTPSConnection
from json import dumps, loads


class RestClient:
    domain = "api.dataforseo.com"
    # 请求超时（秒）：防止 HTTP 连接在无响应时无限等待
    timeout = 60

    def __init__(self, username, password):
        self.username = username
        self.password = password

    def request(self, path, method, data=None):
        connection = HTTPSConnection(self.domain, timeout=self.timeout)
        try:
            base64_bytes = b64encode(
                ("%s:%s" % (self.username, self.password)).encode("ascii")
            ).decode("ascii")
            headers = {'Authorization': 'Basic %s' % base64_bytes, 'Content-Encoding': 'gzip'}
            connection.request(method, path, headers=headers, body=data)
            response = connection.getresponse()
            return loads(response.read().decode())
        finally:
            connection.close()

    def get(self, path):
        return self.request(path, 'GET')

    def post(self, path, data):
        if isinstance(data, str):
            data_str = data
        else:
            data_str = dumps(data)
        return self.request(path, 'POST', data_str)
