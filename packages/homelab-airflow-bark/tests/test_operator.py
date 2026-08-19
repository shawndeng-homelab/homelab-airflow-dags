"""Tests for the explicit Bark notification operator."""

from homelab_airflow_bark.bark_client import BarkResponse
from homelab_airflow_bark.operators import BarkNotifyOperator


def test_operator_delegates_to_connection_backed_hook(mocker) -> None:
    """Keep explicit notifications as retryable Airflow tasks."""
    hook_class = mocker.patch("homelab_airflow_bark.operators.BarkHook")
    hook_class.return_value.send.return_value = BarkResponse(
        url="https://bark.internal/push",
        status_code=200,
        ok=True,
        payload={"code": 200},
    )
    operator = BarkNotifyOperator(
        task_id="notify",
        message={"title": "Done", "body": "Upload finished"},
    )

    result = operator.execute({})

    assert result["ok"] is True
    hook_class.assert_called_once_with("bark_default", timeout=None)
    assert hook_class.return_value.send.call_args.args[0].title == "Done"
