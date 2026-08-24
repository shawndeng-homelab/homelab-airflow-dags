# homelab-airflow-providers-bilibili

Apache Airflow 2.11 provider for publishing reviewed video artifacts to Bilibili through the pinned `biliup==1.2.2` Python SDK.

## Connection

Create `bilibili_default` with connection type `bilibili`. Credentials are never stored in Airflow Connection fields; mount the biliup `cookies.json` file as a read-only Secret and configure only its path:

```json
{
  "credential_path": "/var/run/secrets/bilibili/cookies.json",
  "account_id": "main",
  "submit_api": "web",
  "proxy": null
}
```

The Hook performs a read-only login check. It does not renew or overwrite the mounted credential file.

## Operators

`BilibiliUploadOperator` accepts a `BilibiliUploadRequest` and local paths or `Artifact` objects. Artifact inputs are materialized from RustFS through the official Amazon `S3Hook` and verified against size/SHA-256. `BilibiliArchiveLookupOperator` fetches a normalized remote snapshot (including status and remote part identities) through `get_video_info`. `BilibiliAppendOperator` accepts a `BilibiliArchiveSnapshot` plus `BilibiliAppendRequest`. It checks `expected_part_count` as an optimistic concurrency guard, then uploads new parts by submitting the complete archive, preserving existing remote part filenames and metadata.

The DAG should use a publication registry or manifest idempotency key before invoking either operator. A retry after an uncertain submission must reconcile the remote archive before uploading again.

The current implementation keeps biliup-specific imports inside `client.BiliupSdkAdapter`; DAGs and contracts do not import biliup classes. The Python SDK's internal append implementation is therefore covered by adapter tests and must be revalidated whenever biliup is upgraded.

## Scope boundaries

- Cover upload is part of the publish transaction, not a standalone task.
- Description, tags, category, copyright, dynamic, scheduled time, and moderation flags are request metadata.
- `BilibiliPublicationSensor` polls with `mode="reschedule"` and fails closed on rejection. RustFS materialization, archive lookup, and the publication registry boundary is implemented. `AirflowVariablePublicationRegistry` is available for low-concurrency DAGs; concurrent production workflows should use a transactional database implementation of the same protocol.
- Do not log cookies, access tokens, raw connection objects, presigned URLs, or unredacted SDK responses.
