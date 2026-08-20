"""Patch the Airflow 2.11 footer with the installed DAG package version."""

from html import escape
from importlib.metadata import distribution
from importlib.metadata import version
from pathlib import Path


PACKAGE_NAME = "homelab-airflow-dags"
AIRFLOW_TEMPLATE = Path("airflow/www/templates/airflow/main.html")
ORIGINAL_FOOTER = (
    "          {{ version_label }}: {% if airflow_version %}"
    '<a href="https://pypi.python.org/pypi/apache-airflow/{{ airflow_version }}" '
    'target="_blank" rel="noopener noreferrer">v{{ airflow_version }}</a>'
    "{% else %} N/A{% endif %}\n"
    "          {% if git_version %}<br>Git Version: <strong>{{ git_version }}</strong>{% endif %}"
)


def patch_footer(template: str, package_version: str) -> str:
    """Return the Airflow template with the image package version in its footer."""
    if template.count(ORIGINAL_FOOTER) != 1:
        raise RuntimeError("Expected the Airflow 2.11 footer exactly once; its template may have changed")

    replacement = (
        "          Airflow Version: {% if airflow_version %}"
        '<a href="https://pypi.python.org/pypi/apache-airflow/{{ airflow_version }}" '
        'target="_blank" rel="noopener noreferrer">v{{ airflow_version }}</a>'
        "{% else %} N/A{% endif %}\n"
        f"          <br>{PACKAGE_NAME} Version: <strong>v{escape(package_version)}</strong>"
    )
    return template.replace(ORIGINAL_FOOTER, replacement)


def main() -> None:
    """Patch the template installed by the apache-airflow distribution."""
    template_path = Path(distribution("apache-airflow").locate_file(AIRFLOW_TEMPLATE))
    template = template_path.read_text(encoding="utf-8")
    template_path.write_text(patch_footer(template, version(PACKAGE_NAME)), encoding="utf-8")


if __name__ == "__main__":
    main()
