from importlib.metadata import PackageNotFoundError
from importlib.metadata import version

from homelab_airflow_bark.bark_client import BarkClient
from homelab_airflow_bark.bark_client import BarkResponse
from homelab_airflow_bark.schemas import BarkPushMessage


try:
    __version__ = version("homelab-airflow-bark")
except PackageNotFoundError:
    __version__ = "0.0.0"

__all__ = ["BarkClient", "BarkPushMessage", "BarkResponse", "__version__"]
