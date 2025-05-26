import sys

import requests


if sys.version_info >= (3, 8):
    from importlib.metadata import version
from importlib_metadata import version


def query_pypi(package_name: str) -> dict | None:
    """Query PyPI for the available versions of a package.

    Args:
        package_name (str): The name of the package to query.

    Returns:
        dict: A dictionary containing the available versions of the package.
    """
    url = f"https://pypi.org/pypi/{package_name}/json"
    response = requests.get(url)
    if response.status_code == 200:
        data = response.json()
        versions = list(data["releases"].keys())
        return versions
    return None


def query_current_version(package_name: str) -> str | None:
    """Query current version of a package installed in the environment.

    Args:
        package_name (str): The name of the package to query.

    Returns:
        str: The current version of the package installed in the environment.
    """
    try:
        pkg_version = version(package_name)
        return pkg_version
    except Exception:
        return None


if __name__ == "__main__":
    package_name = "apache-airflow"
    versions = query_current_version(package_name)
    print(f"Versions for {package_name}: {versions}")
