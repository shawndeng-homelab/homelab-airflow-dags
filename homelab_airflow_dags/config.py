"""Configuration management module for Consul-based settings.

This module provides a centralized configuration management system using HashiCorp Consul
as the backend storage. It supports dynamic configuration loading with caching mechanisms
and hot-reload capabilities for environment variables.

The module automatically constructs configuration keys using the pattern:
`{CONFIG_PREFIX}/{PROJECT_NAME}/{config_name}` where CONFIG_PREFIX defaults to 'cfg'
and PROJECT_NAME defaults to 'homelab-airflow-dags'.

Environment Variables:
    PROJECT_NAME: Name of the project (default: 'homelab-airflow-dags')
    CONFIG_PREFIX: Prefix for configuration keys (default: 'cfg')
    CONSUL_HOST: Consul server hostname (default: 'localhost')
    CONSUL_PORT: Consul server port (default: '8500')
    CONSUL_TOKEN: Consul authentication token (optional)

Example:
    Basic usage for getting and setting configurations:

    ```python
    from homelab_airflow_dags.config import get_config, set_config

    # Get configuration with default fallback
    db_config = get_config("database_config", {"host": "localhost"})
    ```

Note:
    The Consul client is cached using LRU cache with maxsize=1 to optimize performance
    while still supporting hot-reload when environment variables change.
"""

import os
from functools import lru_cache
from typing import Any

import consul
import yaml


PROJECT_NAME = os.getenv("PROJECT_NAME", "homelab-airflow-dags")


@lru_cache(maxsize=1)
def _create_consul_client(host: str, port: int, token: str):
    """Create a cached Consul client instance.

    This function creates and caches a Consul client based on the provided parameters.
    The cache has a maximum size of 1, meaning only one client instance is cached at a time.
    When parameters change, the old client is evicted and a new one is created.

    Args:
        host: Consul server hostname.
        port: Consul server port number.
        token: Consul authentication token. Can be empty string if no auth required.

    Returns:
        consul.Consul: A configured Consul client instance.
    """
    return consul.Consul(host=host, port=port, token=token, scheme="https")


def get_consul_client():
    """Get a Consul client with hot-reload support for environment variables.

    This function retrieves a Consul client that automatically updates when
    environment variables change. It uses LRU caching to optimize performance
    while maintaining the ability to pick up configuration changes at runtime.

    Returns:
        consul.Consul: A configured Consul client instance.

    Environment Variables:
        CONSUL_HOST: Consul server hostname (default: 'localhost')
        CONSUL_PORT: Consul server port (default: '8500')
        CONSUL_TOKEN: Consul authentication token (default: '')
    """
    host = os.getenv("CONSUL_HOST", "localhost")
    port = int(os.getenv("CONSUL_PORT", "8500"))
    token = os.getenv("CONSUL_TOKEN", "")
    return _create_consul_client(host, port, token)


def _build_config_key(config_name: str) -> str:
    """Build a configuration key path for Consul storage.

    Constructs a hierarchical key path using the pattern:
    cfg/{PROJECT_NAME}/{config_name}

    Args:
        config_name: The name of the configuration item.

    Returns:
        str: The full configuration key path.

    Example:
        >>> _build_config_key("database_settings")
        'cfg/homelab-airflow-dags/database_settings'
    """
    return f"cfg/{PROJECT_NAME}/{config_name}"


def get_config(config_name: str, default: Any = None) -> Any:
    """Retrieve configuration from Consul with YAML parsing.

    Fetches configuration data from Consul using the specified config name,
    automatically parsing YAML content and returning the parsed object.
    If the configuration doesn't exist or parsing fails, returns the default value.

    Args:
        config_name: The name of the configuration to retrieve.
        default: Default value to return if config is not found or parsing fails.

    Returns:
        Any: The parsed configuration object, or default value if not found/invalid.

    Raises:
        No exceptions are raised. All errors are handled gracefully by returning
        the default value.

    Example:
        >>> config = get_config("api_settings", {"timeout": 30})
        >>> print(config.get("timeout"))
        30
    """
    try:
        client = get_consul_client()
        key = _build_config_key(config_name)
        _, data = client.kv.get(key)
        if data is None:
            return default
        yaml_content = data["Value"].decode("utf-8")
        return yaml.safe_load(yaml_content)
    except yaml.YAMLError:
        return default
    except Exception:
        return default


if __name__ == "__main__":
    from pprint import pprint

    result = get_config("risk_portfolio_config")
    pprint(result)
