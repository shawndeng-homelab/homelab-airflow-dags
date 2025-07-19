"""Portfolio Risk Management Task Module.

This module provides Airflow task functions for portfolio risk management
analysis and optimization. It integrates with the ibkr_quant library to
perform comprehensive portfolio optimization using modern portfolio theory
and generates formatted risk analysis reports.

The module is designed to work with Consul for configuration management,
allowing dynamic parameter updates without code changes. It serves as the
core execution engine for portfolio risk management workflows in Airflow.

Example:
    Import and use the task in an Airflow DAG:

    ```python
    from homelab_airflow_dags.common_tasks.risk_management_task import risk_management_task

    @dag(schedule="@daily")
    def my_risk_dag():
        risk_management_task()
    ```

Note:
    This module requires:
    - Consul configuration service with "risk_portfolio_config" key
    - ibkr_quant library for risk management functionality
    - Proper Airflow task environment setup
"""

from airflow.decorators import task
from ibkr_quant.risk_management.display import PortfolioDisplay
from ibkr_quant.risk_management.pypfopt_risk import StrategyBuilder
from ibkr_quant.risk_management.settings import StrategyConfig

from homelab_airflow_dags.config import get_config


@task()
def risk_management_task():
    """Execute comprehensive portfolio risk management analysis and optimization.

    This Airflow task performs a complete portfolio risk management workflow
    that includes configuration loading, strategy building, optimization
    execution, and report generation. The task integrates with Consul for
    dynamic configuration management and uses the ibkr_quant library for
    sophisticated portfolio optimization algorithms.

    The task follows a structured workflow:
    1. Retrieves portfolio configuration from Consul
    2. Creates and validates strategy configuration
    3. Builds portfolio optimizer with specified parameters
    4. Executes optimization algorithms
    5. Generates and displays formatted portfolio analysis

    The function uses modern portfolio theory principles to optimize asset
    allocation based on risk tolerance, expected returns, and constraints
    defined in the configuration. Results are displayed as a formatted
    table for easy analysis and decision-making.

    Returns:
        None: This function outputs results to stdout via print statements
              and does not return any value. The portfolio analysis is
              displayed as a formatted table in the task logs.

    Raises:
        KeyError: If the "risk_portfolio_config" key is not found in Consul
                  or if required configuration parameters are missing.
        ValidationError: If the strategy configuration validation fails due
                        to invalid parameter values or constraints.
        OptimizationError: If the portfolio optimization algorithm fails to
                          converge or encounters numerical issues.
        ConnectionError: If unable to connect to Consul configuration service
                        or external data sources required for optimization.

    Note:
        This task is designed for use in Airflow DAGs and requires:
        - Active Consul service with proper configuration
        - Valid "risk_portfolio_config" in Consul containing:
          * Risk tolerance parameters
          * Expected return assumptions
          * Asset allocation constraints
          * Optimization algorithm settings
        - Network access to data sources for portfolio analysis

    Example:
        Configuration structure in Consul for "risk_portfolio_config":

        ```json
        {
            "risk_tolerance": 0.15,
            "expected_returns": {...},
            "constraints": {...},
            "optimization_method": "efficient_frontier"
        }
        ```

        Task execution in Airflow DAG:

        ```python
        @dag(schedule="@daily")
        def portfolio_dag():
            # Execute daily risk analysis
            risk_analysis = risk_management_task()
        ```

    See Also:
        StrategyConfig: Configuration class for portfolio optimization parameters.
        StrategyBuilder: Factory class for creating portfolio optimizers.
        PortfolioDisplay: Utility class for formatting portfolio analysis results.
        get_config: Function for retrieving configuration from Consul.
    """
    # Load portfolio configuration from Consul
    config = get_config("risk_portfolio_config")

    # Create and validate strategy configuration
    strategy_config = StrategyConfig(**config)

    # Build portfolio optimizer from configuration
    optimizer = StrategyBuilder.build_from_config(strategy_config)

    # Execute portfolio optimization algorithms
    optimizer.execute()

    # Retrieve optimization results and portfolio information
    portfolio_info = optimizer.get_info()

    # Display formatted portfolio analysis table
    print(PortfolioDisplay.to_pretty_table(portfolio_info))
