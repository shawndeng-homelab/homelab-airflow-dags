"""Apache Airflow provider for public YouTube discovery."""

from importlib.metadata import PackageNotFoundError
from importlib.metadata import version


try:
    __version__ = version("homelab-airflow-providers-youtube")
except PackageNotFoundError:
    __version__ = "0.0.0"

__all__ = ["__version__"]
