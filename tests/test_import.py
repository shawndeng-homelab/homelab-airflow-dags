"""Import Test."""

import importlib
import pkgutil

import homelab_airflow_dags # noqa

def test_imports():
    """Test import modules."""
    prefix = "{}.".format(homelab_airflow_dags.__name__) # noqa
    iter_packages = pkgutil.walk_packages(
        homelab_airflow_dags.__path__,  # noqa
        prefix,
    )
    for _, name, _ in iter_packages:
        module_name = name if name.startswith(prefix) else prefix + name
        importlib.import_module(module_name)