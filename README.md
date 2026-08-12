# homelab-airflow-dags

### Overview

Apache Airflow DAGs for the homelab cluster (`homelab_airflow_dags`). DAGs use
the TaskFlow API, are scheduled in UTC, and resolve runtime config/secrets from
Consul via `homelab-config`.

### Workspace layout

This repository is a uv workspace. Packages live under `packages/`.

| Package | Description |
|---------|-------------|
| `homelab-airflow-dags` | Airflow DAGs package (TaskFlow API, Consul-backed config). |

### Development

```bash
uvx --from rust-just just init
uvx --from rust-just just lint
uvx --from rust-just just test-all
```

Local CeleryExecutor Airflow stack (postgres + redis) via podman-compose:

```bash
just podman-compose-up
```
