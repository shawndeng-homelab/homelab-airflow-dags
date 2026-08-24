from typing import ClassVar

from homelab_airflow_providers_bilibili.registry import AirflowVariablePublicationRegistry
from homelab_airflow_providers_bilibili.registry import publication_storage_key
from homelab_video_contracts import BilibiliPublicationRecord


class FakeVariable:
    values: ClassVar[dict[str, str]] = {}

    @classmethod
    def get(cls, key, default_var=None):
        return cls.values.get(key, default_var)

    @classmethod
    def set(cls, key, value):
        cls.values[key] = value


def test_storage_key_is_stable_and_bounded() -> None:
    first = publication_storage_key(source_video_id="yt/1", account_id="main", request_sha256="a" * 64)
    second = publication_storage_key(source_video_id="yt/1", account_id="main", request_sha256="a" * 64)
    assert first == second
    assert first.startswith("bilibili_publication_")
    assert "/" not in first


def test_airflow_variable_registry_round_trip(monkeypatch) -> None:
    import airflow.models

    FakeVariable.values = {}
    monkeypatch.setattr(airflow.models, "Variable", FakeVariable)
    registry = AirflowVariablePublicationRegistry()
    record = BilibiliPublicationRecord(
        source_video_id="yt-1",
        account_id="main",
        request_sha256="b" * 64,
        aid=2,
        bvid="BV2",
    )
    assert registry.get(source_video_id="yt-1", account_id="main", request_sha256="b" * 64) is None
    assert registry.upsert(record) == record
    assert registry.get(source_video_id="yt-1", account_id="main", request_sha256="b" * 64) == record
