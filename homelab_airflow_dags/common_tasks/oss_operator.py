"""MinIO Upload Task Module.

Simple MinIO upload functionality using Consul configuration.
Supports both file-based and memory-based uploads.
"""

import mimetypes
import os
from pathlib import Path
from urllib.parse import quote_plus

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
    """Get the MIME type for a file based on its extension.

    Args:
        file_path: Path to the file

    Returns:
        str: MIME type string
    """
    # Initialize mimetypes if not already done
    mimetypes.init()

    # Get MIME type based on file extension
    content_type, _ = mimetypes.guess_type(file_path)

    # Default to binary if type cannot be determined
    if content_type is None:
        content_type = "application/octet-stream"

    return content_type


def upload_file(file_path: str, object_key: str, bucket_name="airflow", config_name: str = "minio_auth_config") -> bool:
    """Upload a file to MinIO/OSS.

    Args:
        file_path: Local file path to upload
        bucket_name: Target bucket name
        object_key: Target object key/path in the bucket
        config_name: Consul configuration name for MinIO

    Returns:
        bool: True if upload successful, False otherwise

    Example:
        success = upload_file("/tmp/data.pkl", "my-bucket", "data/result.pkl")
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
