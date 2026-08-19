# homelab-airflow-bark

面向 Apache Airflow 2.11 的 Bark Provider，提供：

- BarkNotifier：标准 Airflow 生命周期通知。
- BarkHook：使用 Airflow Connection 发送消息。
- BarkNotifyOperator：需要任务依赖、重试和 XCom 时使用的显式通知任务。
- BarkClient：Airflow 之外可以复用的 HTTP 客户端。

## 安装与发现

本仓库开发环境：

    just init

安装完成后可以在 Airflow Provider 列表中看到 homelab-airflow-bark，并在 Connection Type 下拉列表中看到 Bark。

Linux 或 Airflow 容器内可以检查：

    airflow providers list
    airflow providers hooks

修改 Provider 包或 Connection 配置后，需要重启 Airflow webserver、scheduler 和使用该包的 worker。

## 配置 Bark Connection

默认约定：

    Connection ID: bark_default
    Connection type: bark
    Host: https://bark.example.internal
    Password: Bark device key
    Extra:
      timeout: 10
      verify_tls: true

字段含义：

| Airflow 字段 | 必填 | 用途 |
| --- | --- | --- |
| Connection ID | 是 | 默认使用 bark_default，也可以创建多个设备连接 |
| Connection Type | 是 | 固定为 bark |
| Host | 是 | Bark 服务根地址，必须包含 http 或 https |
| Password | 是 | Bark device key，Airflow 会按密码字段处理 |
| Extra.timeout | 否 | HTTP 请求超时秒数，默认 10 |
| Extra.verify_tls | 否 | 是否验证 TLS 证书，默认 true |

Device key 不应出现在 DAG、消息参数、XCom、Variable 或普通日志中。

### Airflow UI

进入 Admin → Connections → Add：

1. Connection Id 填 bark_default。
2. Connection Type 选择 Bark。
3. Bark server URL 填 Bark 服务地址。
4. Device key 填设备密钥。
5. Extra 填 timeout 和 verify_tls。

Test Connection 只验证字段是否完整和合法，不会真的向手机发送测试通知。

### Airflow CLI

PowerShell 示例：

    $arguments = @(
        'connections',
        'add',
        'bark_default',
        '--conn-type',
        'bark',
        '--conn-host',
        'https://bark.example.internal',
        '--conn-password',
        $env:BARK_DEVICE_KEY
    )
    airflow @arguments

Extra 可以在 UI 中补充，也可以通过部署系统直接创建完整 Connection。

### 环境变量

不希望写入 Airflow metadata database 时，可以在部署系统中生成 JSON Connection：

    $connection = @{
        conn_type = 'bark'
        host = 'https://bark.example.internal'
        password = $env:BARK_DEVICE_KEY
        extra = @{
            timeout = 10
            verify_tls = $true
        }
    } | ConvertTo-Json -Compress

    $env:AIRFLOW_CONN_BARK_DEFAULT = $connection

生产环境应由 Kubernetes Secret、External Secrets 或其他 Secret Manager 注入，不要提交到仓库。

## DAG 失败通知

最常见的用法是在 DAG 级别设置失败 callback：

    from datetime import UTC
    from datetime import datetime

    from airflow import DAG
    from airflow.operators.empty import EmptyOperator
    from homelab_airflow_bark.notifications import BarkNotifier

    dag_failure = BarkNotifier(
        title='Airflow DAG 失败',
        body='''DAG: {{ dag.dag_id }}
    Task: {{ ti.task_id }}
    Run: {{ run_id }}
    Try: {{ ti.try_number }}
    Exception: {{ exception }}''',
        group='airflow-failure',
        level='timeSensitive',
        bark_conn_id='bark_default',
    )

    with DAG(
        dag_id='video_localization',
        start_date=datetime(2026, 1, 1, tzinfo=UTC),
        schedule=None,
        catchup=False,
        on_failure_callback=dag_failure,
    ):
        EmptyOperator(task_id='start')

## Task 级成功、失败和重试通知

同一个 Notifier 可以放在 DAG 或单个 Operator 上：

    from airflow.operators.empty import EmptyOperator
    from homelab_airflow_bark.notifications import BarkNotifier

    task_failure = BarkNotifier(
        title='任务失败：{{ ti.task_id }}',
        body='DAG {{ dag.dag_id }} / Run {{ run_id }}\n{{ exception }}',
        group='airflow-task-failure',
    )

    task_retry = BarkNotifier(
        title='任务即将重试：{{ ti.task_id }}',
        body='当前尝试次数：{{ ti.try_number }}',
        group='airflow-retry',
        level='active',
    )

    task_success = BarkNotifier(
        title='任务完成：{{ ti.task_id }}',
        body='DAG {{ dag.dag_id }} 已完成任务。',
        group='airflow-success',
        level='passive',
    )

    process = EmptyOperator(
        task_id='process_video',
        retries=2,
        on_failure_callback=task_failure,
        on_retry_callback=task_retry,
        on_success_callback=task_success,
    )

Airflow 2.11 允许 callback 使用列表，可以同时发送 Bark 和其他通知：

    on_failure_callback=[
        BarkNotifier(
            title='任务失败',
            body='{{ dag.dag_id }} / {{ ti.task_id }}',
        ),
        another_notifier,
    ]

## Jinja 模板上下文

BarkNotifier 会在发送前使用 Airflow context 渲染以下字段：

- title
- body
- subtitle
- markdown
- url
- group
- icon
- sound
- copy_text

常用模板变量：

| 变量 | 示例 |
| --- | --- |
| dag.dag_id | DAG ID |
| ti.task_id | Task ID |
| run_id | 当前 DagRun ID |
| logical_date | 逻辑执行时间 |
| data_interval_start | 数据窗口开始 |
| data_interval_end | 数据窗口结束 |
| ti.try_number | 当前尝试次数 |
| exception | 失败 callback 中的异常 |
| params | DAG 或 Task 参数 |

不要把 Connection Password、presigned URL 或其他 Secret 渲染到通知正文。

## BarkNotifier 参数

| 参数 | 必填 | 默认值 | 说明 |
| --- | --- | --- | --- |
| title | 是 | 无 | 通知标题，支持模板 |
| body | 是 | 无 | 通知正文，支持模板 |
| bark_conn_id | 否 | bark_default | Airflow Connection ID |
| timeout | 否 | Connection 配置 | 单次通知的超时覆盖值 |
| subtitle | 否 | None | 副标题 |
| markdown | 否 | None | Markdown 内容 |
| level | 否 | active | critical、active、timeSensitive 或 passive |
| url | 否 | None | 点击通知后打开的 URL |
| group | 否 | None | Bark 消息分组 |
| icon | 否 | None | 图标 URL |
| sound | 否 | None | Bark 声音名称 |
| badge | 否 | None | 非负角标数字 |
| call | 否 | false | 是否使用来电式提醒 |
| copy_text | 否 | None | 可复制到剪贴板的文本 |
| auto_copy | 否 | false | 是否自动复制 |
| is_archive | 否 | false | 是否保存到 Bark 历史 |

富通知示例：

    publish_success = BarkNotifier(
        title='Bilibili 投稿完成',
        subtitle='{{ params.channel_name }}',
        body='视频已经发布。',
        markdown='发布任务已完成，可以点击通知查看视频。',
        url='https://www.bilibili.com/video/{{ params.bvid }}',
        icon='https://www.bilibili.com/favicon.ico',
        group='bilibili-publish',
        sound='minuet',
        level='active',
        is_archive=True,
    )

## 使用 BarkNotifyOperator

当通知必须表现为一个独立 Airflow Task 时使用 Operator，例如：

- 通知需要显式上下游依赖。
- 通知失败必须让任务失败。
- 希望使用 Airflow retries 和 retry_delay。
- 下游需要读取 Bark 响应 XCom。

    from datetime import timedelta

    from homelab_airflow_bark.operators import BarkNotifyOperator

    notify = BarkNotifyOperator(
        task_id='notify_publish_success',
        bark_conn_id='bark_default',
        message={
            'title': '上传完成',
            'body': 'Bilibili 视频投稿成功',
            'group': 'bilibili',
            'level': 'active',
            'is_archive': True,
        },
        retries=2,
        retry_delay=timedelta(seconds=30),
    )

Operator 返回的 XCom：

    {
        'url': 'https://bark.example.internal/push',
        'status_code': 200,
        'ok': True,
        'payload': {
            'code': 200,
        },
    }

Callback 和 Operator 的失败语义不同：

| 组件 | 通知失败后的行为 |
| --- | --- |
| BarkNotifier | BaseNotifier 记录异常，不覆盖原 Task 状态 |
| BarkNotifyOperator | Operator 失败，可以按 Airflow 配置重试 |

## 直接使用 BarkHook

自定义 Airflow 组件中可以复用 Hook：

    from homelab_airflow_bark.hooks import BarkHook

    response = BarkHook(
        bark_conn_id='bark_default',
        timeout=5,
    ).send(
        {
            'title': '处理完成',
            'body': '视频本地化任务已完成。',
            'group': 'video-localization',
        }
    )

Hook 会读取 Connection、验证消息并返回 BarkResponse。

## Airflow 之外使用客户端

    from homelab_airflow_bark.bark_client import BarkClient
    from homelab_airflow_bark.schemas import BarkPushMessage

    client = BarkClient(
        base_url='https://bark.example.internal',
        device_key='device-key',
        timeout=10,
        verify_tls=True,
    )

    response = client.send(
        BarkPushMessage(
            title='Done',
            body='Task finished',
            group='standalone',
        )
    )

    print(response.status_code)

Airflow 之外没有 Connection Secret 管理能力，调用方需要自行保护 device key。

## 从旧消息格式迁移

旧格式把服务和凭据放在消息中：

    message={
        'base_url': 'https://bark.example.internal',
        'device_key': 'device-key',
        'title': 'Done',
        'body': 'Upload finished',
    }

新格式只包含通知内容：

    message={
        'title': 'Done',
        'body': 'Upload finished',
    }

并在 Operator 或 Notifier 上引用 Connection：

    bark_conn_id='bark_default'

base_url 和 device_key 已不再是 BarkPushMessage 字段。迁移后凭据不会进入 DAG 序列化、模板上下文或 XCom。

## 运行与安全说明

- Bark 使用同步 HTTP 请求，callback 应保持简短。
- callback 通知是 best effort，不应用作事务提交或业务状态持久化。
- Test Connection 不发送真实通知。
- verify_tls 在生产环境应保持 true。
- 不要在异常信息、通知正文或日志中输出 device key。
- 多个设备或环境应创建不同的 Connection ID。
- Windows 原生 Airflow 只适合有限开发验证，Provider discovery 的最终验收应在 Linux 容器或部署环境完成。
