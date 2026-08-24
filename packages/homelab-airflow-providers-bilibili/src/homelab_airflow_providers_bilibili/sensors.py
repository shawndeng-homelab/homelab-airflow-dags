"""Reschedule sensor for Bilibili publication review and release."""

from __future__ import annotations

from typing import Any

from airflow.exceptions import AirflowException
from airflow.sensors.base import BaseSensorOperator
from airflow.sensors.base import PokeReturnValue
from airflow.utils.context import Context
from homelab_video_contracts import BilibiliPublicationStatus

from homelab_airflow_providers_bilibili.hooks import BilibiliHook


class BilibiliPublicationSensor(BaseSensorOperator):
    """Wait until a remote archive reaches an allowed lifecycle status."""

    template_fields = ("aid", "bilibili_conn_id")

    def __init__(
        self,
        *,
        aid: int,
        allowed_statuses: tuple[BilibiliPublicationStatus | str, ...] = (BilibiliPublicationStatus.PUBLISHED,),
        bilibili_conn_id: str = BilibiliHook.default_conn_name,
        **kwargs: Any,
    ) -> None:
        kwargs.setdefault("mode", "reschedule")
        super().__init__(**kwargs)
        if aid <= 0:
            raise ValueError("aid must be positive")
        if not allowed_statuses:
            raise ValueError("allowed_statuses must not be empty")
        self.aid = aid
        self.allowed_statuses = frozenset(BilibiliPublicationStatus(status) for status in allowed_statuses)
        self.bilibili_conn_id = bilibili_conn_id

    def poke(self, context: Context) -> PokeReturnValue:
        snapshot = BilibiliHook(self.bilibili_conn_id).get_archive(int(self.aid))
        if snapshot.status is BilibiliPublicationStatus.REJECTED:
            raise AirflowException(f"Bilibili archive {snapshot.aid} was rejected")
        if snapshot.status not in self.allowed_statuses:
            self.log.info(
                "Bilibili archive pending: aid=%s status=%s",
                snapshot.aid,
                snapshot.status.value,
            )
            return PokeReturnValue(is_done=False)
        return PokeReturnValue(is_done=True, xcom_value=snapshot.model_dump(mode="json"))
