import pytest
from homelab_airflow_providers_bilibili import sensors
from homelab_video_contracts import BilibiliArchiveSnapshot
from homelab_video_contracts import BilibiliPublicationStatus


def _snapshot(status: BilibiliPublicationStatus) -> BilibiliArchiveSnapshot:
    return BilibiliArchiveSnapshot(aid=1, bvid="BV1", title="demo", status=status)


class FakeHook:
    snapshot = _snapshot(BilibiliPublicationStatus.REVIEWING)

    def __init__(self, conn_id):
        self.conn_id = conn_id

    def get_archive(self, aid):
        return self.snapshot


def test_publication_sensor_reschedules_until_published(monkeypatch) -> None:
    monkeypatch.setattr(sensors, "BilibiliHook", FakeHook)
    sensor = sensors.BilibiliPublicationSensor(task_id="wait", aid=1)
    assert sensor.poke({}).is_done is False
    FakeHook.snapshot = _snapshot(BilibiliPublicationStatus.PUBLISHED)
    result = sensor.poke({})
    assert result.is_done is True
    assert result.xcom_value["status"] == "published"


def test_publication_sensor_fails_on_rejected(monkeypatch) -> None:
    monkeypatch.setattr(sensors, "BilibiliHook", FakeHook)
    FakeHook.snapshot = _snapshot(BilibiliPublicationStatus.REJECTED)
    sensor = sensors.BilibiliPublicationSensor(task_id="wait", aid=1)
    with pytest.raises(Exception, match="rejected"):
        sensor.poke({})
