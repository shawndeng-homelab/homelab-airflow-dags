from homelab_airflow_providers_bilibili.get_provider_info import get_provider_info


def test_provider_info_declares_bilibili_connection_and_entry_modules() -> None:
    info = get_provider_info()
    assert info["package-name"] == "homelab-airflow-providers-bilibili"
    assert info["connection-types"][0]["connection-type"] == "bilibili"
    assert info["connection-types"][0]["hook-class-name"].endswith("hooks.BilibiliHook")
    assert info["operators"][0]["python-modules"] == ["homelab_airflow_providers_bilibili.operators"]
    assert info["sensors"][0]["python-modules"] == ["homelab_airflow_providers_bilibili.sensors"]
