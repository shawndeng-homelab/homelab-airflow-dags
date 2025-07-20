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
from ibkr_quant.risk_management.pypfopt_risk import StrategyBuilder
from ibkr_quant.risk_management.settings import StrategyConfig

from homelab_airflow_dags.config import get_config


@task
def risk_management_task() -> dict:
    """Execute comprehensive portfolio risk management analysis and optimization.

    This Airflow task performs end-to-end portfolio risk management analysis using
    modern portfolio theory and optimization algorithms. It loads configuration from
    Consul, builds a portfolio optimization strategy, executes the optimization
    algorithms, and returns detailed portfolio analysis results.

    The task integrates with the ibkr_quant library's StrategyBuilder to perform:
    - Portfolio composition analysis and optimization
    - Risk metrics calculation (VaR, CVaR, Sharpe ratio, etc.)
    - Expected returns and volatility analysis
    - Efficient frontier computation
    - Portfolio performance attribution

    The function is designed to be configuration-driven, allowing portfolio
    parameters to be dynamically updated through Consul without code changes.
    This enables flexible portfolio management workflows and easy parameter
    tuning for different market conditions.

    Returns:
        dict: A comprehensive dictionary containing portfolio optimization results
            and risk analysis metrics. The dictionary includes:
            - portfolio_weights: Optimized asset allocation weights
            - expected_returns: Expected return for each asset
            - risk_metrics: Calculated risk measures (VaR, CVaR, volatility)
            - performance_metrics: Portfolio performance indicators
            - optimization_details: Technical optimization results
            - market_data: Underlying market data used in analysis

    Raises:
        ValueError: If the Consul configuration "risk_portfolio_config" is not found
            or contains invalid parameters that cannot be validated by StrategyConfig.
        ConfigurationError: If the strategy configuration fails validation due to
            missing required fields or invalid parameter combinations.
        OptimizationError: If the portfolio optimization algorithms fail to converge
            or encounter numerical issues during execution.
        DataError: If required market data is unavailable or contains insufficient
            historical data for reliable optimization.
        ConnectionError: If unable to connect to external data sources or services
            required for portfolio analysis.

    Note:
        This task requires the following external dependencies and configurations:
        - Active Consul service with "risk_portfolio_config" key containing:
          * asset_symbols: List of ticker symbols for portfolio assets
          * optimization_method: Portfolio optimization algorithm to use
          * risk_parameters: Risk management configuration parameters
          * data_source_config: Market data source configuration
        - Network connectivity to market data providers
        - Sufficient computational resources for optimization algorithms
        - Valid API credentials for data sources (if required)

    Example:
        Basic usage in an Airflow DAG:

        ```python
        from homelab_airflow_dags.common_tasks.risk_management_task import risk_management_task

        @dag(schedule="@daily")
        def portfolio_optimization_dag():
            # Execute daily portfolio optimization
            results = risk_management_task()

            # Use results in downstream tasks
            generate_report(results)
        ```

        Consul configuration example for "risk_portfolio_config":

        ```json
        {
            "asset_symbols": ["AAPL", "GOOGL", "MSFT", "TSLA"],
            "optimization_method": "max_sharpe",
            "risk_free_rate": 0.02,
            "lookback_period": 252,
            "data_source": "yahoo_finance",
            "risk_parameters": {
                "max_volatility": 0.20,
                "min_weight": 0.05,
                "max_weight": 0.40
            }
        }
        ```

    See Also:
        StrategyBuilder: The core portfolio optimization engine from ibkr_quant.
        StrategyConfig: Configuration validation and management class.
        get_config: Consul configuration retrieval function.
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
    return optimizer.get_info().model_dump()
