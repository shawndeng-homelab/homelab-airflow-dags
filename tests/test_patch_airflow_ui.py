from pathlib import Path
from runpy import run_path

import pytest


PATCH_MODULE = run_path(Path(__file__).parents[1] / "docker" / "patch_airflow_ui.py", run_name="patch_airflow_ui")
ORIGINAL_FOOTER = PATCH_MODULE["ORIGINAL_FOOTER"]
patch_footer = PATCH_MODULE["patch_footer"]


def test_patch_footer_replaces_git_revision_with_package_version():
    """The footer keeps Airflow's version and shows the installed DAG version."""
    patched = patch_footer(f"before\n{ORIGINAL_FOOTER}\nafter", "0.4.2")

    assert "Airflow Version:" in patched
    assert "homelab-airflow-dags Version: <strong>v0.4.2</strong>" in patched
    assert "Git Version:" not in patched
    assert "{{ airflow_version }}" in patched


def test_patch_footer_rejects_an_unexpected_airflow_template():
    """An upstream template change fails instead of silently skipping the patch."""
    with pytest.raises(RuntimeError, match="template may have changed"):
        patch_footer("footer changed upstream", "0.4.2")
