"""Portfolio Risk Management DAG Module.

This module defines an Airflow DAG for daily portfolio risk management analysis
and optimization using the ibkr_quant library. The DAG performs comprehensive
risk analysis, portfolio optimization, and generates formatted reports.

The DAG is designed to run daily and integrates with Consul for configuration
management and the ibkr_quant library for risk management functionality.

Example:
    The DAG can be triggered manually or runs automatically on a daily schedule:

    ```bash
    # Manual trigger via Airflow CLI
    airflow dags trigger risk_management
    ```

Attributes:
    risk_management_dag: The instantiated DAG object for Airflow to discover.

Note:
    This module requires:
    - Consul configuration service with "risk_portfolio_config" key
    - ibkr_quant library for risk management functionality
    - Proper Airflow environment setup
"""

import json
import tempfile
from datetime import datetime

from airflow.decorators import dag
from airflow.decorators import task

from homelab_airflow_dags.common_tasks.oss_operator import upload_file
from homelab_airflow_dags.common_tasks.risk_management_task import risk_management_task
from homelab_airflow_dags.constants import PACKAGE_NAME


# DAG documentation in English for better compatibility
_DAG_DOC_MD = """
# Portfolio Risk Management DAG

## Overview
This DAG performs daily portfolio risk management analysis and optimization
to support investment decision-making processes.

## Key Features
- **Risk Metrics Calculation**: Computes portfolio risk indicators including volatility, VaR, maximum drawdown
- **Portfolio Optimization**: Asset allocation optimization based on modern portfolio theory
- **Risk Report Generation**: Generates formatted risk analysis reports for review
- **Data Persistence**: Serializes and uploads portfolio results to MinIO object storage
- **Configuration Management**: Dynamic risk management parameter management via Consul

## Execution Flow
1. Load risk portfolio configuration parameters from Consul
2. Create and validate strategy configuration objects
3. Build portfolio optimizer
4. Execute optimization algorithms to calculate optimal asset allocation
5. Generate and return portfolio analysis results
6. Serialize portfolio results to temporary JSON file and generate file paths
7. Upload serialized data to MinIO object storage using dedicated upload task

## Technical Dependencies
- **ibkr_quant**: Provides risk management and portfolio optimization functionality
- **Consul**: Configuration management service for storing risk parameters
- **MinIO**: Object storage service for persisting portfolio analysis results
- **Airflow**: Workflow scheduling and management platform

## Configuration Requirements
Requires `risk_portfolio_config` key in Consul with parameters:
- Risk tolerance settings
- Expected return parameters
- Asset allocation constraints
- Optimization algorithm parameters

## Schedule
- **Frequency**: Daily execution (@daily)
- **Start Date**: January 1, 2025
- **Concurrency**: Single instance only
- **Catchup**: Disabled

## Output
Upon completion, the DAG produces:
- **Log Output**: Formatted portfolio analysis tables in task logs including:
  * Asset allocation weights
  * Risk metric values
  * Optimization recommendations
- **Persistent Storage**: Serialized PortfolioInfo object uploaded to MinIO at:
  * Path format: `portfolio_analysis/YYYY-MM-DD/portfolio_info_YYYYMMDD_HHMMSS.json`
  * Bucket: `portfolio-results` (configurable)
"""


@dag(
    "risk_management",
    description="Daily portfolio risk management analysis and optimization",
    doc_md=_DAG_DOC_MD,
    tags=["risk", "ibkr", "portfolio", "optimization"],
    start_date=datetime(2025, 1, 1),
    schedule="@daily",
    catchup=False,
    max_active_runs=1,
)
def risk_management():
    """Define the portfolio risk management DAG with data persistence.

    This function creates an Airflow DAG that performs daily portfolio risk
    management analysis and optimization, followed by data serialization and
    upload to MinIO object storage. The DAG executes a comprehensive risk
    analysis workflow that includes portfolio optimization, risk metric
    calculation, result serialization, and persistent storage.

    The DAG is configured to run daily and uses Consul for configuration
    management, allowing for dynamic parameter updates without code changes.
    It integrates with the ibkr_quant library to perform sophisticated
    portfolio optimization using modern portfolio theory, and stores results
    in MinIO for long-term persistence and analysis.

    Returns:
        None: This function defines the DAG structure and task dependencies.
              The actual DAG object is created by the @dag decorator.

    Note:
        This function is decorated with @dag and serves as the DAG definition.
        The actual execution logic is implemented in the task functions.

        Key features:
        - Daily execution schedule
        - Single active run limitation
        - No historical backfill
        - Consul-based configuration management
        - Comprehensive risk analysis and optimization
        - Automatic data persistence to MinIO object storage

    Example:
        The DAG structure created by this function:

        ```
        risk_management_dag
        ├── risk_management_task (generates PortfolioInfo)
        ├── serialize_portfolio (serializes to file and returns paths)
        └── upload_minio (uploads file to MinIO storage)
        ```

    See Also:
        risk_management_task: The main task that performs the risk analysis.
        serialize_and_upload_portfolio: Task that serializes and uploads results.
        StrategyBuilder: The portfolio optimization engine from ibkr_quant.
        PortfolioDisplay: The report formatting utility from ibkr_quant.
    """

    @task
    def serialize_portfolio(portfolio_info):
        """Serialize PortfolioInfo object to a temporary file and return file paths.

        This task serializes the portfolio analysis results using JSON format
        and saves them to a temporary file. It returns both the local file path
        and the target MinIO object key for subsequent upload operations.

        Note:
            Due to Airflow's XCom serialization mechanism, the portfolio_info parameter
            may be received as a dictionary instead of a PortfolioInfo object when
            passed between tasks. This function handles both cases automatically.

        Args:
            portfolio_info: The PortfolioInfo object or dict containing portfolio analysis results

        Returns:
            dict: A dictionary containing:
                - file_path: Local path to the serialized JSON file
                - object_key: Target object key for MinIO storage
                - bucket_name: Target bucket name for MinIO storage
        """
        # Generate object key with timestamp for MinIO storage
        now = datetime.now()
        date_str = now.strftime("%Y-%m-%d")
        timestamp_str = now.strftime("%Y%m%d_%H%M%S")
        object_key = f"{PACKAGE_NAME}/risk_portfolio/{date_str}/portfolio_info_{timestamp_str}.json"

        # Create temporary file for serialization
        # Note: We manually manage the file lifecycle to ensure it persists for upload
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", encoding="utf-8") as temp_file:
            try:
                json_string = json.dumps(portfolio_info, indent=2, default=str, ensure_ascii=False)
                temp_file.write(json_string)
                temp_file.flush()
                file_path = temp_file.name
                upload_file(file_path, object_key)
            finally:
                temp_file.close()

        return {"file_path": file_path, "object_key": object_key, "bucket_name": "airflow"}

    # Execute the main risk management analysis task
    portfolio_results: dict = risk_management_task()
    # Execute serialization task to get file paths
    serialize_portfolio(portfolio_results)


# Instantiate the DAG for Airflow discovery
risk_management_dag = risk_management()
