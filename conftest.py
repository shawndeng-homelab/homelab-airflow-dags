"""Repository-wide pytest initialization."""

import os
from pathlib import Path


airflow_home = os.environ.get("AIRFLOW_HOME")
if airflow_home and not os.path.isabs(airflow_home):
    os.environ["AIRFLOW_HOME"] = str((Path.cwd() / airflow_home).resolve())
