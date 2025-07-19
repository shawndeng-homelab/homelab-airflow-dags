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

from datetime import datetime

from airflow.decorators import dag

from homelab_airflow_dags.common_tasks.risk_management_task import risk_management_task


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
- **Configuration Management**: Dynamic risk management parameter management via Consul

## Execution Flow
1. Load risk portfolio configuration parameters from Consul
2. Create and validate strategy configuration objects
3. Build portfolio optimizer
4. Execute optimization algorithms to calculate optimal asset allocation
5. Generate and output formatted portfolio analysis reports

## Technical Dependencies
- **ibkr_quant**: Provides risk management and portfolio optimization functionality
- **Consul**: Configuration management service for storing risk parameters
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
Upon completion, outputs formatted portfolio analysis tables in logs including:
- Asset allocation weights
- Risk metric values
- Optimization recommendations
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
    """Define the portfolio risk management DAG.

    This function creates an Airflow DAG that performs daily portfolio risk
    management analysis and optimization. The DAG executes a comprehensive
    risk analysis workflow that includes portfolio optimization, risk metric
    calculation, and report generation.

    The DAG is configured to run daily and uses Consul for configuration
    management, allowing for dynamic parameter updates without code changes.
    It integrates with the ibkr_quant library to perform sophisticated
    portfolio optimization using modern portfolio theory.

    Returns:
        None: This function defines the DAG structure and task dependencies.
              The actual DAG object is created by the @dag decorator.

    Note:
        This function is decorated with @dag and serves as the DAG definition.
        The actual execution logic is implemented in the risk_management_task.

        Key features:
        - Daily execution schedule
        - Single active run limitation
        - No historical backfill
        - Consul-based configuration management
        - Comprehensive risk analysis and optimization

    Example:
        The DAG structure created by this function:

        ```
        risk_management_dag
        └── risk_management_task
        ```

    See Also:
        risk_management_task: The main task that performs the risk analysis.
        StrategyBuilder: The portfolio optimization engine from ibkr_quant.
        PortfolioDisplay: The report formatting utility from ibkr_quant.
    """
    # Execute the main risk management analysis task
    risk_management_task()


# Instantiate the DAG for Airflow discovery
risk_management_dag = risk_management()
