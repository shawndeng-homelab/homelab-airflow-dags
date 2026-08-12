"""Configuration manager for Airflow DAGs using Consul key-value store.

This module provides a high-level interface for accessing centralized configurations
stored in Consul. It automatically handles environment-specific settings, key
namespacing, and data type conversions. The module is designed to work seamlessly
with the Homelab configuration system.

The configuration path in Consul follows this pattern:
    cfg/<package-name>/<key>

For example, if your package name is "homelab-airflow-dags" and you request
the key "database/mysql", it will look for:
    cfg/homelab-airflow-dags/database/mysql

Environment Variables:
    HOMELAB_ENVIRONMENT: Runtime environment (dev/staging/prod).
    HOMELAB_CONSUL_URLS: Comma-separated list of Consul server URLs.
    HOMELAB_CONSUL_TOKEN: Consul ACL Token for authentication.

Example:
    >>> from homelab_airflow_dags.config import get_config
    >>> # Get risk portfolio settings
    >>> risk_config = get_config("risk_portfolio_config")
    >>> if risk_config:
    ...     threshold = risk_config.get("risk_threshold")
    ...     window_size = risk_config.get("window_size")
    >>> # Get data source configuration
    >>> source_config = get_config("data_source/market")
"""

from homelab_config import create_client

from homelab_airflow_dags.constants import PACKAGE_NAME


def get_config(key: str) -> dict | str | None:
    """Fetch and parse configuration from Consul key-value store.

    This function automatically prepends the package namespace to the provided key
    and handles data type conversion based on the stored value format.

    Args:
        key: Configuration key path relative to the package namespace.
             Example keys:
             - "risk_portfolio_config" -> For risk management settings
             - "data_source/market" -> For market data source configuration
             - "notification/slack" -> For Slack notification settings

    Returns:
        The configuration value with appropriate type conversion:
            - dict: For JSON-formatted values (automatically parsed)
            - str: For plain text values
            - None: If the key doesn't exist

    Raises:
        ConnectionError: If unable to connect to Consul
        ValueError: If stored value cannot be parsed
        TypeError: If key is not a string

    Examples:
        >>> config = get_config("risk_portfolio_config")
        >>> if config and isinstance(config, dict):
        ...     threshold = config.get("risk_threshold", 0.05)
        ...     window = config.get("window_size", 252)
    """
    tool_name = PACKAGE_NAME.replace("_", "-")
    _key = f"cfg/{tool_name}/{key}"
    client = create_client()
    return client(_key)
