"""Dynamic DAG loader for Apache Airflow using YAML configuration files.

This module provides functionality to dynamically load and generate Apache Airflow DAGs
from YAML configuration files using the dagfactory library. It searches for YAML files
in configured directories and automatically generates DAGs based on their definitions.

The module supports multiple configuration directories through environment variables and
provides a default fallback to the standard Airflow DAGs folder.

Environment Variables:
    CONFIG_ROOT_DIRS: Colon-separated list of directories containing DAG YAML files.
                      Example: "/path/to/dags:/another/path/to/dags"
    AIRFLOW_PROJ_DIR: Base directory for the Airflow project (default: /opt/airflow).

Typical usage example:
    # This module is typically imported by Airflow to automatically load DAGs
    # The main() function is executed when the module is imported

    # YAML files should be placed in:
    # 1. Directories specified in CONFIG_ROOT_DIRS environment variable
    # 2. Default location: $AIRFLOW_PROJ_DIR/dags/

    # Example YAML structure:
    # my_dag:
    #   default_args:
    #     owner: 'airflow'
    #     start_date: '2024-01-01'
    #   schedule_interval: '@daily'
    #   tasks:
    #     task_1:
    #       operator: airflow.operators.bash.BashOperator
    #       bash_command: 'echo "Hello World"'

Note:
    This module automatically executes the main() function when imported,
    which will load all DAGs from YAML files found in the configured directories.
"""

import glob
import logging
import os

from dagfactory import DagFactory


logger = logging.getLogger(__name__)


def load_dag_floders() -> list[str]:
    """Load directories containing DAG YAML files.

    Returns:
        list[str]: A list of directories containing YAML files.
    """
    floders: list[str] = []

    dag_factory_dirs = os.getenv("CONFIG_ROOT_DIRS")
    if dag_factory_dirs:
        result = dag_factory_dirs.split(os.pathsep)
        floders.extend(result)

    default_dags_floder = os.path.join(os.getenv("AIRFLOW_PROJ_DIR", "/opt/airflow"), "dags")
    floders.append(default_dags_floder)
    return [os.path.normpath(item) for item in set(floders)]


def find_yamls(config_root_dir: str) -> list[str]:
    """Find all YAML files in the specified directories.

    Args:
        config_root_dir (str): A colon-separated string of directories to search for YAML files.

    Returns:
        list[str]: A sorted list of paths to YAML files found in the specified directories.
    """
    yamls = glob.glob(os.path.join(config_root_dir, "**", "*.y[a]ml"), recursive=True)
    return sorted(yamls)


def load_dags(yaml_files: list[str]) -> None:
    """Load DAGs from the specified YAML files.

    Args:
        yaml_files (list[str]): A list of paths to YAML files containing DAG definitions.
    """
    for index, yaml_file in enumerate(yaml_files):
        logger.info(f"Loaded: {yaml_file}")
        dag_factory = DagFactory(str(yaml_file))
        if index == 0:
            # Clean existing DAGs only for the first file to avoid conflicts
            dag_factory.clean_dags(globals())
            logger.info("Cleaning existing DAGs...")

        dag_factory.generate_dags(globals())
        logger.info(f"Loaded: {yaml_file}")


def main() -> None:
    """Main function to load DAGs from YAML files."""
    config_root_dirs = load_dag_floders()
    logger.info(f"Config root dirs: {config_root_dirs}")

    yaml_files = []
    for item in config_root_dirs:
        logger.info(f"Searching for YAML files in: {item}")
        yaml_paths: list[str] = find_yamls(item)
        yaml_files.extend(yaml_paths)

    load_dags(yaml_files)


info = main()
