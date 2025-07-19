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


# Chinese documentation for the DAG
DOC_MD = """
# 投资组合风险管理 DAG

## 概述
这个 DAG 每天自动执行投资组合风险管理分析，为投资决策提供数据支持。

## 主要功能
- **风险指标计算**: 计算投资组合的各项风险指标，包括波动率、VaR、最大回撤等
- **投资组合优化**: 基于现代投资组合理论进行资产配置优化
- **风险报告生成**: 生成格式化的风险分析报告，便于查看和分析
- **配置管理**: 通过 Consul 动态管理风险管理参数

## 执行流程
1. 从 Consul 加载风险投资组合配置参数
2. 创建策略配置对象并验证参数
3. 构建投资组合优化器
4. 执行优化算法计算最优资产配置
5. 生成并输出格式化的投资组合分析报告

## 技术依赖
- **ibkr_quant**: 提供风险管理和投资组合优化功能
- **Consul**: 配置管理服务，存储风险管理参数
- **Airflow**: 工作流调度和管理平台

## 配置要求
需要在 Consul 中配置 `risk_portfolio_config` 键，包含以下参数：
- 风险容忍度设置
- 预期收益率参数
- 资产配置约束条件
- 优化算法参数

## 执行时间
- **调度频率**: 每天执行一次 (@daily)
- **开始时间**: 2025年1月1日
- **并发限制**: 同时只允许一个实例运行
- **历史回填**: 禁用 (catchup=False)

## 输出结果
DAG 执行完成后会在日志中输出格式化的投资组合分析表格，包含：
- 资产配置权重
- 风险指标数值
- 优化建议信息
"""


@dag(
    "risk_management",
    description="Daily portfolio risk management analysis and optimization",
    doc_md=DOC_MD,
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
