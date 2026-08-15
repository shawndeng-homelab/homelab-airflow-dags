from importlib.metadata import PackageNotFoundError, version

__author__ = "Shawn Deng"
__email__ = "shawndeng1109@qq.com"

try:
    __version__ = version("homelab-airflow-dags")
except PackageNotFoundError:
    __version__ = "0.0.0"
