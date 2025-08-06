from datetime import datetime
from datetime import timedelta
from typing import Any

from polygon import RESTClient

from homelab_airflow_dags.config import get_secrets


def get_polygon_client() -> RESTClient:
    """获取 Polygon API 客户端."""
    api_token = get_secrets("polygonio")["Api"]["homelab"]
    return RESTClient(api_key=api_token)


def get_aapl_quotes() -> list[dict[str, Any]]:
    """获取 AAPL 股票近两年的 quotes 数据.

    Returns:
        list[dict]: 包含 quotes 数据的列表
    """
    client = get_polygon_client()

    # 计算时间范围: 当前时间往前推两年
    end_date = datetime.now()
    start_date = end_date - timedelta(days=1)  # 大约两年

    # 格式化日期为 YYYY-MM-DD 格式
    start_date_str = start_date.strftime("%Y-%m-%d")
    end_date_str = end_date.strftime("%Y-%m-%d")


    quotes_data = []

    try:
        # 注意: 由于数据量可能很大, 这里使用分页获取
        quotes = client.list_quotes(
            ticker="AAPL",
            timestamp_gte=start_date_str,
            timestamp_lte=end_date_str,
            limit=500  # 每次请求的最大数据量
        )

        for quote in quotes:
            quote_data = {
                'timestamp': quote.timestamp,
                'timeframe': quote.timeframe,
                'bid': quote.bid,
                'bid_size': quote.bid_size,
                'ask': quote.ask,
                'ask_size': quote.ask_size,
                'exchange': quote.exchange,
                'sip_timestamp': quote.sip_timestamp
            }
            quotes_data.append(quote_data)

        print(f"成功获取 {len(quotes_data)} 条 quotes 数据")

    except Exception as e:
        print(f"获取数据时发生错误: {e!s}")
        raise

    return quotes_data




if __name__ == "__main__":
    # 测试获取数据
    print("开始获取 AAPL quotes 数据...")

    # 获取每日聚合数据 (推荐, 数据量较小)
    daily_quotes = get_aapl_quotes()
    print(f"获取到 {len(daily_quotes)} 条每日数据")
