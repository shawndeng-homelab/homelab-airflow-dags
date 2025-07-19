"""MinIO Upload Task Module.

Simple MinIO upload functionality using Consul configuration.
Supports both file-based and memory-based uploads.
"""

import io
import json
import os
import pickle
from typing import Any

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

    # Create connection URI for environment variable
    # Format: aws://access_key:secret_key@?endpoint_url=...&region_name=...
    from urllib.parse import quote_plus

    access_key = quote_plus(config["access_key"])
    secret_key = quote_plus(config["secret_key"])
    endpoint_url = quote_plus(config["minio_endpoint"])

    conn_uri = f"aws://{access_key}:{secret_key}@?endpoint_url={endpoint_url}&region_name={region}"

    # Set the environment variable
    env_var_name = f"AIRFLOW_CONN_{conn_id.upper()}"
    os.environ[env_var_name] = conn_uri

    # Return S3Hook using the connection ID
    return S3Hook(aws_conn_id=conn_id)


def upload_python_object(
    obj: Any, bucket_name: str, object_key: str, format_type: str = "pickle", config_name: str = "minio_auth_config"
) -> bool:
    """Upload a Python object to MinIO.

    Args:
        obj: Python object to upload
        bucket_name: Target bucket name
        object_key: Target object key/path
        format_type: Serialization format ("pickle", "json")
        config_name: Consul configuration name

    Returns:
        bool: True if upload successful, False otherwise
    """
    try:
        s3_hook = get_minio_s3_hook(config_name)

        # Serialize object based on format
        if format_type == "pickle":
            buffer = io.BytesIO()
            pickle.dump(obj, buffer)
            buffer.seek(0)
        elif format_type == "json":
            json_str = json.dumps(obj, ensure_ascii=False, indent=2)
            buffer = io.BytesIO(json_str.encode("utf-8"))
        else:
            raise ValueError(f"Unsupported format_type: {format_type}")

        # Upload to MinIO
        s3_hook.load_file_obj(file_obj=buffer, key=object_key, bucket_name=bucket_name, replace=True)

        logger.info(f"Successfully uploaded Python object to {bucket_name}/{object_key}")
        return True

    except Exception as e:
        logger.error(f"Failed to upload Python object: {e}")
        return False
