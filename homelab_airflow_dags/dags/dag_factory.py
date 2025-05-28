import glob
import logging
import os

import dagfactory


logger = logging.getLogger(__name__)


def load_dag_floders() -> list[str]:
    """Load directories containing DAG YAML files.

    Returns:
        list[str]: A list of directories containing YAML files.
    """
    floders: list[str] = []

    dag_factory_dirs = os.getenv("CONFIG_ROOT_DIRS")
    if dag_factory_dirs:
        dag_factory_dirs.split(os.pathsep)
        floders.extend(dag_factory_dirs)

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
    for yaml_file in yaml_files:
        dag_factory = dagfactory.DagFactory(str(yaml_file))
        dag_factory.clean_dags(globals())
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
