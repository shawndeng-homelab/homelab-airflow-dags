# homelab-airflow-bark

Reusable Bark notification components for homelab Airflow DAGs.

This package keeps Bark integration out of DAG code. DAGs only pass a validated `message`, while Pydantic handles field checks and serialization.

## Components

`schemas.py`

- `BarkPushMessage`: validated Bark payload model
- Validates `base_url`, `device_key`, `title`, `body`, `level`, and optional fields such as `subtitle`, `markdown`, `url`, and `group`
- Normalizes Bark-specific fields like `autoCopy` and `isArchive`

`bark_client.py`

- `BarkClient`: sends a validated message to `POST /push`
- Returns a `BarkResponse` model with `url`, `status_code`, `ok`, and response `payload`

`operators.py`

- `BarkNotifyOperator`: Airflow operator for notifications
- Accepts a single `message` argument as either a plain `dict` or a `BarkPushMessage`
- Supports Apache Airflow 2.11.0 and imports BaseOperator from airflow.models.

## Message Fields

| Field | Required | Type | Default | Notes |
| --- | --- | --- | --- | --- |
| `base_url` | Yes | URL | - | Bark server base URL, for example `http://bark.default.svc.cluster.local:8080` |
| `device_key` | Yes | string | - | Target device key in Bark |
| `title` | Yes | string | - | Notification title |
| `body` | Yes | string | - | Notification body |
| `subtitle` | No | string | `None` | Short subtitle shown under the title |
| `markdown` | No | string | `None` | Markdown content for rich text pushes |
| `level` | No | string | `active` | One of `critical`, `active`, `timeSensitive`, `passive` |
| `url` | No | URL | `None` | Click-through URL |
| `group` | No | string | `None` | Notification group key |
| `icon` | No | URL | `None` | Icon URL |
| `sound` | No | string | `None` | Notification sound name |
| `badge` | No | integer | `None` | Badge count, must be non-negative |
| `call` | No | bool | `False` | Whether to ring like a call alert |
| `copy` | No | string | `None` | Clipboard value to copy |
| `auto_copy` | No | bool | `False` | Auto-copy the notification content |
| `is_archive` | No | bool | `False` | Archive the notification in Bark |

## Usage

```python
from homelab_airflow_bark.operators import BarkNotifyOperator

notify = BarkNotifyOperator(
    task_id="notify_bark",
    message={
        "base_url": "http://bark.default.svc.cluster.local:8080",
        "device_key": "{{ var.value.bark_device_key }}",
        "title": "Upload complete",
        "body": "YouTube video was uploaded successfully.",
        "subtitle": "biliup",
        "auto_copy": True,
        "level": "active",
    },
)
```

Use `markdown`, `url`, `group`, `sound`, `icon`, or `badge` when you need richer push notifications.

For direct calls outside Airflow:

```python
from homelab_airflow_bark.bark_client import BarkClient
from homelab_airflow_bark.schemas import BarkPushMessage

client = BarkClient()
message = BarkPushMessage(
    base_url="http://bark.default.svc.cluster.local:8080",
    device_key="device-key",
    title="Done",
    body="Task finished successfully.",
)
response = client.send(message)
```

## Design Notes

- Keep the Airflow operator thin.
- Keep validation in Pydantic models.
- Keep HTTP transport in the client.
- Prefer a single `message` object in DAGs instead of many operator parameters.

## Runtime Notes

- Bark server expects `POST /push` with JSON payload.
- `device_key` is an application-level token in the payload, not HTTP auth.
- The package targets Python 3.12 and Airflow 3.2+.

