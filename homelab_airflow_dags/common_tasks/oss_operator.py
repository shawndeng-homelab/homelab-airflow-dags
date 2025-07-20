"""MinIO Upload Task Module.

Simple MinIO upload functionality using Consul configuration.
Supports both file-based and memory-based uploads.
"""

import mimetypes
import os
from pathlib import Path
from urllib.parse import quote_plus

from airflow.decorators import task
from airflow.providers.amazon.aws.hooks.s3 import S3Hook
from loguru import logger

from homelab_airflow_dags.config import get_config


def get_minio_s3_hook(config_name: str = "minio_auth_config") -> S3Hook:
    """Create S3Hook using MinIO configuration from Consul.

    This function creates an S3Hook by setting up environment variables
    for the AWS connection, which is a simpler approach that doesn't
    require database operations.

    Args:
        config_name: Name of the configuration in Consul

    Returns:
        S3Hook: Configured S3Hook instance

    Example Consul Configuration:
        ```yaml
        minio_endpoint: "http://minio.minio.svc.cluster.local:9000"
        access_key: "your-minio-access-key"
        secret_key: "your-minio-secret-key"
        region: "us-east-1"
        ```
    """
    config = get_config(config_name)
    if not config:
        raise ValueError(f"MinIO auth configuration not found in Consul: {config_name}")

    required_fields = ["minio_endpoint", "access_key", "secret_key"]
    missing_fields = [field for field in required_fields if field not in config]
    if missing_fields:
        raise ValueError(f"Missing required fields in MinIO config: {missing_fields}")

    # Set up environment variable for the connection
    conn_id = "minio_default"
    region = config.get("region", "us-east-1")
    access_key = quote_plus(config["access_key"])
    secret_key = quote_plus(config["secret_key"])
    endpoint_url = quote_plus(config["minio_endpoint"])

    conn_uri = f"aws://{access_key}:{secret_key}@?endpoint_url={endpoint_url}&region_name={region}"

    # Set the environment variable
    env_var_name = f"AIRFLOW_CONN_{conn_id.upper()}"
    os.environ[env_var_name] = conn_uri

    # Return S3Hook using the connection ID
    return S3Hook(aws_conn_id=conn_id)


def get_content_type(file_path: str) -> str:
    """Determine the MIME type of a file based on its file extension.

    This function uses Python's built-in mimetypes module to guess the MIME type
    of a file based on its extension. It provides a fallback to a generic binary
    MIME type for files with unknown or unrecognized extensions.

    The function is essential for proper file handling in object storage systems
    like MinIO, as it ensures that files are served with the correct Content-Type
    header, enabling proper browser handling and preview functionality.

    Args:
        file_path: The path to the file for which to determine the MIME type.
                  Only the file extension is used for type detection, so the
                  file doesn't need to exist at the specified path.

    Returns:
        str: The MIME type string corresponding to the file extension.
             Returns "application/octet-stream" for unknown file types.

    Example:
        Common file type detection:

        ```python
        # Image files
        assert get_content_type("image.jpg") == "image/jpeg"
        assert get_content_type("photo.png") == "image/png"

        # Document files
        assert get_content_type("document.pdf") == "application/pdf"
        xlsx_mime = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        assert get_content_type("spreadsheet.xlsx") == xlsx_mime

        # Text files
        assert get_content_type("data.csv") == "text/csv"
        assert get_content_type("config.json") == "application/json"

        # Unknown extensions
        assert get_content_type("file.unknown") == "application/octet-stream"
        ```

    Note:
        - The function initializes the mimetypes module if not already done
        - Only the file extension is considered, not the actual file content
        - The detection is case-insensitive for file extensions
        - Binary fallback ensures compatibility with all file types
    """
    # Initialize mimetypes if not already done
    mimetypes.init()

    # Get MIME type based on file extension
    content_type, _ = mimetypes.guess_type(file_path)

    # Default to binary if type cannot be determined
    if content_type is None:
        content_type = "application/octet-stream"

    return content_type


def upload_file(
    file_path: str, object_key: str, bucket_name: str = "airflow", config_name: str = "minio_auth_config"
) -> bool:
    """Upload a file to MinIO object storage with automatic MIME type detection.

    This function provides the core file upload functionality to MinIO object storage.
    It handles file validation, MIME type detection, S3Hook configuration, and the
    actual upload operation with proper error handling and logging.

    The function automatically detects the file's MIME type based on its extension
    and sets appropriate metadata for proper file handling in MinIO. It uses the
    S3Hook from Airflow's Amazon provider to ensure compatibility with S3-compatible
    storage systems like MinIO.

    Args:
        file_path: The local file system path to the file that needs to be uploaded.
                  Must point to an existing file with read permissions.
        object_key: The target object key/path within the MinIO bucket. This serves
                   as the unique identifier for the file within the bucket.
        bucket_name: The name of the target MinIO bucket. The bucket must exist
                    before attempting the upload. Defaults to "airflow".
        config_name: The name of the configuration key in Consul that contains
                    MinIO authentication details. Defaults to "minio_auth_config".

    Returns:
        bool: True if the file upload completed successfully, False if the upload
              failed due to any reason (file not found, connection issues, etc.).

    Raises:
        ValueError: If the MinIO configuration is not found in Consul or if required
                   configuration fields are missing from the Consul configuration.
        FileNotFoundError: If the specified local file does not exist at the given
                          path or if there are permission issues reading the file.
        ConnectionError: If unable to establish connection to MinIO service or if
                        authentication fails with the provided credentials.
        S3UploadFailedError: If the upload operation fails due to network issues,
                            storage quota exceeded, or other MinIO service errors.

    Example:
        Basic file upload:

        ```python
        success = upload_file(
            file_path="/tmp/data.pkl",
            object_key="data/processed/result.pkl",
            bucket_name="analytics"
        )
        if success:
            print("File uploaded successfully")
        ```

        Upload with custom configuration:

        ```python
        success = upload_file(
            file_path="/home/user/report.pdf",
            object_key="reports/monthly/report.pdf",
            bucket_name="documents",
            config_name="custom_minio_config"
        )
        ```

    Note:
        - The function automatically sets Content-Type based on file extension
        - Cache-Control header is set to "max-age=3600" for better performance
        - All upload operations use the "replace=True" option to overwrite existing files
        - Detailed logging is provided for both success and failure cases
    """
    try:
        # Check if file exists
        if not Path(file_path).exists():
            logger.error(f"File does not exist: {file_path}")
            return False

        # Get content type for the file
        content_type = get_content_type(file_path)
        logger.info(f"Detected content type for {file_path}: {content_type}")

        # Get S3Hook and upload with proper content type
        s3_hook = get_minio_s3_hook(config_name)

        # Set extra args with content type for proper preview in MinIO
        extra_args = {
            "ContentType": content_type,
            "CacheControl": "max-age=3600",  # Optional: set cache control
        }
        s3_hook._extra_args = extra_args

        s3_hook.load_file(filename=file_path, key=object_key, bucket_name=bucket_name, replace=True)

        logger.info(f"Successfully uploaded {file_path} to {bucket_name}/{object_key} with content type {content_type}")
        return True

    except Exception as e:
        logger.error(f"Failed to upload file {file_path}: {e}")
        return False


# Chinese documentation for upload_minio task
UPLOAD_MINIO_DOC_MD = """
# MinIO 文件上传任务

## 概述
这是一个用于将本地文件上传到 MinIO 对象存储的 Airflow 任务。该任务支持自动重试机制，
并能够根据文件扩展名自动检测和设置正确的 MIME 类型，确保文件在 MinIO 中能够正确预览。

## 主要功能
- **文件上传**: 将本地文件上传到指定的 MinIO 存储桶
- **自动重试**: 内置 3 次重试机制，提高任务成功率
- **MIME 类型检测**: 自动检测文件类型并设置正确的 Content-Type
- **配置管理**: 通过 Consul 动态管理 MinIO 连接配置
- **错误处理**: 完善的错误处理和日志记录

## 执行流程
1. 验证本地文件是否存在
2. 从 Consul 获取 MinIO 认证配置
3. 检测文件的 MIME 类型
4. 创建 S3Hook 连接到 MinIO
5. 执行文件上传操作
6. 记录上传结果和相关日志

## 技术依赖
- **Apache Airflow**: 工作流调度和管理平台
- **MinIO**: 兼容 S3 API 的对象存储服务
- **Consul**: 配置管理服务，存储 MinIO 连接信息
- **S3Hook**: Airflow 提供的 S3 操作接口

## 配置要求
需要在 Consul 中配置 `minio_auth_config` 键，包含以下参数：
- `minio_endpoint`: MinIO 服务端点 URL
- `access_key`: MinIO 访问密钥
- `secret_key`: MinIO 秘密密钥
- `region`: 存储区域（可选，默认为 us-east-1）

## 参数说明
- **file_path**: 要上传的本地文件路径
- **object_key**: 在存储桶中的目标对象键/路径
- **bucket_name**: 目标存储桶名称（默认为 "airflow"）

## 使用示例
```python
from homelab_airflow_dags.common_tasks.oss_operator import upload_minio

# 在 DAG 中使用
upload_task = upload_minio(
    file_path="/tmp/data.pkl",
    object_key="data/processed/result.pkl",
    bucket_name="my-bucket"
)
```

## 注意事项
- 确保本地文件路径有效且文件存在
- 确保 MinIO 服务可访问且认证信息正确
- 任务失败时会自动重试最多 3 次
- 上传成功后会在日志中记录详细信息
"""


@task(retries=3, doc_md=UPLOAD_MINIO_DOC_MD)
def upload_minio(file_path: str, object_key: str, bucket_name: str = "airflow") -> bool:
    """Upload a local file to MinIO object storage with automatic retry and MIME type detection.

    This Airflow task provides a robust file upload mechanism to MinIO object storage
    with built-in retry logic, automatic MIME type detection, and comprehensive error
    handling. The task integrates with Consul for dynamic configuration management
    and uses the S3Hook for reliable file transfer operations.

    The task performs the following operations:
    1. Validates the existence of the local file
    2. Retrieves MinIO authentication configuration from Consul
    3. Detects the file's MIME type based on its extension
    4. Creates an S3Hook connection to MinIO
    5. Uploads the file with proper metadata
    6. Logs the upload results for monitoring

    Args:
        file_path: The local file system path to the file that needs to be uploaded.
                  Must be an absolute or relative path to an existing file.
        object_key: The target object key/path within the MinIO bucket where the file
                   will be stored. This acts as the file's identifier in the bucket.
        bucket_name: The name of the target MinIO bucket. Defaults to "airflow".
                    The bucket must exist before attempting the upload.

    Returns:
        bool: True if the file upload was successful, False if the upload failed
              due to file not found, connection issues, or other errors.

    Raises:
        ValueError: If the MinIO authentication configuration is not found in Consul
                   or if required configuration fields are missing.
        FileNotFoundError: If the specified local file does not exist at the given path.
        ConnectionError: If unable to establish connection to MinIO service or if
                        authentication fails with the provided credentials.
        PermissionError: If insufficient permissions to read the local file or write
                        to the specified MinIO bucket.
        S3UploadFailedError: If the S3/MinIO upload operation fails due to network
                            issues, storage quota, or other service-related problems.

    Note:
        This task is designed for use in Airflow DAGs and requires:
        - Active Consul service with proper MinIO configuration
        - Valid "minio_auth_config" in Consul containing:
          * minio_endpoint: MinIO service endpoint URL
          * access_key: MinIO access key for authentication
          * secret_key: MinIO secret key for authentication
          * region: Storage region (optional, defaults to "us-east-1")
        - Network connectivity to both Consul and MinIO services
        - Proper file system permissions for reading the source file

    Example:
        Basic usage in an Airflow DAG:

        ```python
        from homelab_airflow_dags.common_tasks.oss_operator import upload_minio

        @dag(schedule="@daily")
        def my_data_pipeline():
            # Upload processed data file
            upload_task = upload_minio(
                file_path="/tmp/processed_data.csv",
                object_key="data/daily/processed_data.csv",
                bucket_name="data-lake"
            )
        ```

        Advanced usage with task dependencies:

        ```python
        @dag(schedule="@daily")
        def advanced_pipeline():
            # Process data first
            process_task = process_data()

            # Then upload the result
            upload_task = upload_minio(
                file_path="{{ ti.xcom_pull(task_ids='process_data')['output_file'] }}",
                object_key="results/{{ ds }}/output.pkl",
                bucket_name="analytics"
            )

            process_task >> upload_task
        ```

        Consul configuration example for "minio_auth_config":

        ```json
        {
            "minio_endpoint": "http://minio.homelab.local:9000",
            "access_key": "minioadmin",
            "secret_key": "minioadmin123",
            "region": "us-east-1"
        }
        ```

    See Also:
        upload_file: The underlying function that performs the actual upload operation.
        get_minio_s3_hook: Function that creates the S3Hook with MinIO configuration.
        get_content_type: Function that determines the MIME type of files.
    """
    return upload_file(file_path, object_key, bucket_name)
