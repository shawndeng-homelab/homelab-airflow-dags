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
Only the five keys shown above are accepted. Unknown connection settings, an invalid proxy URL, conflicting credential-path keys, and submit APIs other than `web`/`client` fail explicitly. The proxy is installed on every biliup HTTP session created by the adapter for login, archive lookup, pre-upload, cover, and submit calls.

## Operators

`BilibiliUploadOperator` accepts a `BilibiliUploadRequest` and optional local paths or `Artifact` objects. When `local_parts` is omitted it is derived from `request.parts[*].video`. RustFS inputs are materialized through the official Amazon `S3Hook`, using the path returned by `download_file`, and verified with size plus streaming SHA-256 checks. The new-submission payload uses `bili_webup_sync.Data` and `BiliBili.submit`, which are the `biliup==1.2.2` interfaces that support both `web` and `client` submission.

`BilibiliArchiveLookupOperator` reads the owner-only creative-center `archive` and `videos` payload from `/x/web/archive/view`; it does not rebuild editable data from the public playback page. `BilibiliAppendOperator` requires that complete snapshot, validates `aid`/`bvid` and `expected_part_count`, then submits the preserved archive, every old video object (including `archive`, `desc`, `filename`, and other upload metadata), and the newly uploaded parts through the SDK edit path.

Both mutation operators claim the publication registry key before the remote submit/edit call. A completed record is reused on retry. An `unknown`/in-flight record or any record without reusable `aid` and `bvid` fails closed, so an uncertain retry cannot silently create another submission. `AirflowVariablePublicationRegistry` is the default for low-concurrency DAGs; concurrent production DAGs must inject a transactional implementation whose `claim` operation is backed by a unique constraint.

SDK responses are never returned as raw XCom values. By default they are discarded after normalization. Set `raw_response_uri` to a unique `s3://` RustFS object when an audit copy is required; the operator writes JSON with `replace=False` and returns only `raw_response_uri`.

## Publish settings

The adapter maps every declared setting to the SDK payload. `dolby`, `lossless_music` (`hires`), `no_reprint`, and `charging_pay` work with `web` and `client`. `close_reply`, `selection_reply`, and `close_danmu` map to the client-only `up_*` fields and are rejected when `submit_api=web`. `extra_fields` is flattened by biliup, but it cannot override any SDK-owned field. Unsupported connection settings and SDK field collisions are errors rather than ignored configuration.

The implementation keeps biliup-specific imports inside `client.BiliupSdkAdapter`; DAGs and contracts do not import biliup classes. Payload contract tests pin the behavior of `biliup==1.2.2` and must be revalidated whenever the SDK is upgraded.

## Scope boundaries

- Cover upload is part of the publish transaction, not a standalone task.
- Description, tags, category, copyright, dynamic, scheduled time, and publish settings are request metadata for new submissions. Append requests do not accept `tid` or `tags`; edits preserve these values from the creative-center archive.
- `BilibiliPublicationSensor` polls with `mode="reschedule"` and fails closed on rejection.
- Do not log cookies, access tokens, raw connection objects, presigned URLs, or unredacted SDK responses.
