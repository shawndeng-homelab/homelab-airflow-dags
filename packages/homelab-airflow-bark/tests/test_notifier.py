"""Tests for the standard Airflow Bark notifier."""

from airflow.notifications.basenotifier import BaseNotifier
from homelab_airflow_bark.notifications import BarkNotifier


def test_notifier_is_standard_airflow_notifier() -> None:
    """Expose Bark through the Airflow BaseNotifier protocol."""
    notifier = BarkNotifier(title="Failed", body="Task failed")

    assert isinstance(notifier, BaseNotifier)
    assert "title" in notifier.template_fields
    assert notifier.bark_conn_id == "bark_default"
    assert "device_key" not in notifier.__dict__


def test_notifier_sends_rendered_fields_through_hook(mocker) -> None:
    """Build a validated message and delegate transport to BarkHook."""
    hook_class = mocker.patch("homelab_airflow_bark.notifications.BarkHook")
    notifier = BarkNotifier(title="Failed", body="Task failed", group="airflow")

    notifier.notify({})

    message = hook_class.return_value.send.call_args.args[0]
    assert message.title == "Failed"
    assert message.group == "airflow"
