# homelab-airflow-dags

## 概述

这是 homelab 集群使用的 Apache Airflow DAG 仓库。当前 DAG 主要基于 TaskFlow API 编写，统一使用 UTC 调度，并通过 `homelab-config` 从 Consul 读取运行时配置和密钥。

## Airflow 基础组件

这个仓库会用到几个常见的 Airflow 概念，用来把任务拆分得更清楚、也更方便复用：

- `DAG`：定义完整工作流，以及任务之间的顺序关系。
- `Task` / `Operator`：可复用的执行单元，适合下载、上传、通知、清理等步骤。
- `Sensor`：等待外部条件满足，例如检测 YouTube 是否有新视频。
- `Hook`：封装外部系统访问，把传输逻辑从 DAG 代码里抽出去。
- `Connection` / `Variable`：存放服务地址、凭证和低频变化的配置。
- `XCom`：在单次运行内传递少量数据。
- `Asset`：跨运行记录逻辑资源或游标。
- `TaskGroup`：在 UI 中对相关任务分组，不改变执行逻辑。

## 工作区结构

这是一个 `uv` workspace，代码都放在 `packages/` 下。

| 包名 | 说明 |
|---|---|
| `homelab-airflow-dags` | 主 DAG 包，包含 TaskFlow DAG 和 Consul 配置访问逻辑。 |
| `homelab-airflow-bark` | Bark 通知共享组件包，提供 Bark 客户端和 Airflow Operator。 |
| `homelab-airflow-providers-youtube` | YouTube 视频发现与元数据集成。 |
| `homelab-airflow-providers-localization` | 外部视频本地化服务的异步任务提交与等待。 |
| `homelab-airflow-providers-bilibili` | 哔哩哔哩上传集成。 |
| `homelab-video-contracts` | 视频本地化流程共享的版本化数据契约。 |

## 开发命令

```bash
uvx --from rust-just just init
uvx --from rust-just just lint
uvx --from rust-just just test-all
```

本地启动 CeleryExecutor Airflow 环境（postgres + redis）：

```bash
just podman-compose-up
```

停止本地环境：

```bash
just podman-compose-down
```
