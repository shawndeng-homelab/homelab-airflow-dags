"""Import Test."""

import importlib
import pkgutil

import homelab_airflow_dags


def test_imports(mocker):
    """Test import modules."""
    # 使用 pytest-mocker mock get_config，避免实际连接 Consul
    mocker.patch("homelab_airflow_dags.config.get_config", return_value={})
    prefix = "{}.".format(homelab_airflow_dags.__name__) # noqa
    iter_packages = pkgutil.walk_packages(
        homelab_airflow_dags.__path__,
        prefix,
    )
    for _, name, _ in iter_packages:
        module_name = name if name.startswith(prefix) else prefix + name
        importlib.import_module(module_name)
