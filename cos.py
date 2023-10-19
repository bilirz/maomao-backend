# 第三方库导入
from qcloud_cos import CosConfig, CosS3Client
# 应用/模块内部导入
import config


cos_config = CosConfig(Endpoint=config.COS_ENDPOINT, SecretId=config.COS_SECRET_ID, SecretKey=config.COS_SECRET_KEY)
cos_client = CosS3Client(cos_config)


def upload_to_cos(local_file_path, cos_file_name):
    try:
        cos_client.upload_file(Bucket=config.COS_BUCKET, LocalFilePath=local_file_path, Key=cos_file_name)
    except Exception as e:
        return f'错误: {e}'
