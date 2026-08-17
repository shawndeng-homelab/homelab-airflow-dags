# Airflow 2.11.0 回退迁移计划

## 1. 目标与边界

本分支以远端 `0.11.0` 标签为历史基线，目标是恢复 Apache Airflow `2.11.0`，同时保留当前开发分支中已经完成的工程化成果：

- `uv` workspace 与 `packages/*` 目录结构；
- `homelab-airflow-dags` 主包；
- `homelab-airflow-bark` 包；
- YouTube 与 Bilibili provider 包；
- 当前的文档、CI、发布、Cocogitto、Ruff、pytest 与 `just` 工作流；
- 当前 DAG 和公共任务的业务行为。

本迁移不应简单地把整个仓库恢复为 `0.11.0`。`0.11.0` 仅作为 Airflow 2.11.0 依赖、Docker 镜像、Compose 服务拓扑和兼容 API 的参照；工程结构和新增包以迁移开始时的 `origin/add-youtube-provider` 为准。

特别注意：最新 DevOps 设施属于必须保留的成果，不属于回退范围。`just`、Cocogitto、GitHub Actions、uv workspace、Ruff、pytest、pre-commit、文档构建和发布流程一律以 `origin/add-youtube-provider` 为唯一事实来源。即使 `0.11.0` 中存在同名旧文件，也不得用旧版本覆盖。

### 1.1 回退允许清单

本次只允许修改与 Airflow 运行时兼容直接相关的内容：

- 各 package 中的 Airflow 版本和必要 provider 依赖；
- Python 源码中的 Airflow 3 专属 import、装饰器和运行时 API；
- `docker/Dockerfile` 中的 Airflow 基础镜像、版本参数及相关说明；
- `docker/docker-compose.yaml` 中的 Airflow 服务、命令、健康检查、环境变量和依赖关系；
- 与上述变化直接相关的测试、锁文件和说明文档。

任何不在该清单中的回退都必须先说明其与 Airflow 2.11 兼容性的直接关系，不能仅因为 `0.11.0` 中写法不同就恢复旧版本。

### 1.2 明确保留清单

以下文件和能力必须采用最新开发分支版本，原则上不得从 `0.11.0` 恢复：

- `justfile` 及全部 `just` recipe；
- `cog.toml`、版本管理和 changelog 自动化；
- `.github/workflows/` 下的 CI、测试、文档、版本和发布工作流；
- 根 `pyproject.toml` 的 uv workspace 结构与 `packages/*` members；
- `.pre-commit-config.yaml`、`.ruff.toml`、`.yamlfmt.yaml`；
- MkDocs 配置、文档生成脚本和当前 README；
- Renovate、编辑器配置和当前仓库维护配置；
- 当前多包目录、包元数据、测试布局和发布注册信息。

如果这些设施因 Airflow 版本变化确实需要调整，只允许进行最小兼容修改。例如 CI 中显式写死 `3.2.0` 时可改为 `2.11.0`，但不得恢复旧 workflow、旧 Taskfile 或旧发布流程。

## 2. Git 基线与实施策略

当前迁移分支：`rollback/airflow-2.11.0`

基线标签：`0.11.0`（提交 `e68d8b6`）

### 2.1 首选：使用 Git worktree 隔离迁移

建议保留当前 Airflow 3 开发目录不动，在同级目录创建独立 worktree。这样后续 Agent 可以同时读取两套文件，不需要频繁切换分支，也能降低误改当前开发目录的风险。

在当前仓库目录执行：

```shell
git fetch origin --tags
git fetch origin add-youtube-provider
git worktree add ../homelab-airflow-dags-airflow2 rollback/airflow-2.11.0
```

然后让实施 Agent 在 `../homelab-airflow-dags-airflow2` 中工作。原目录继续保留 `add-youtube-provider`，可作为当前项目结构与新增包的只读参照。

如果迁移分支尚未创建，则改用：

```shell
git worktree add -b rollback/airflow-2.11.0 ../homelab-airflow-dags-airflow2 0.11.0
```

同一个分支不能同时检出到两个 worktree。如果本分支当前已在主工作树中检出，应先让主工作树切回 `add-youtube-provider`，再创建迁移 worktree：

```shell
git switch add-youtube-provider
git worktree add ../homelab-airflow-dags-airflow2 rollback/airflow-2.11.0
```

实施过程中可直接对照两个目录，也可用 Git 对象比较，不要在两个 worktree 中同时修改相同迁移文件。

### 2.2 基线检查

进入迁移 worktree 后执行：

```shell
git fetch origin --tags
git fetch origin add-youtube-provider
git status --short
git rev-parse 0.11.0
git rev-parse origin/add-youtube-provider
```

迁移 worktree 必须干净。不要直接 merge `origin/add-youtube-provider`，因为这会把 Airflow 3 升级提交原样带回。建议采用“当前树迁入后定向回退”的方式：

1. 在本分支上把 `origin/add-youtube-provider` 相对 `0.11.0` 的工程结构、DevOps 设施和包文件完整迁入，以最新开发分支的工作树作为初始内容。
2. 随即按本文后续清单定向改写 Airflow 依赖、Python API、Dockerfile 和 Compose。
3. 将迁入和兼容性修改作为一个可审阅的迁移提交，或拆成下述建议提交序列。

禁止按目录或全仓执行 `git checkout 0.11.0 -- .`。读取旧标签时优先使用 `git show 0.11.0:<path>` 做只读对照；即使处理 Docker Compose，也应把 Airflow 2 语义移植到最新文件，而不是盲目覆盖整个文件。

执行前额外创建一个临时保护引用，例如：

```shell
git branch backup/pre-airflow2-migration origin/add-youtube-provider
```

不得使用 `git reset --hard`、强制推送或删除远端分支来处理冲突。

迁移完成、变更已提交并推送、且确认不再需要独立目录后，才可从主仓库执行：

```shell
git worktree remove ../homelab-airflow-dags-airflow2
git worktree prune
```

不要在 worktree 内直接删除目录；不要在仍有未提交改动时强制移除 worktree。

## 3. 需要保留的当前成果

从 `origin/add-youtube-provider` 迁入并保留以下内容：

- 根目录 workspace 配置：`pyproject.toml`、`uv.lock`、`justfile`；
- `packages/homelab-airflow-dags/`；
- `packages/homelab-airflow-bark/`；
- `packages/homelab-airflow-providers-youtube/`；
- `packages/homelab-airflow-providers-bilibili/`；
- `docs/`、`mkdocs.yml` 和 README；
- `.github/workflows/`、`cog.toml`、Ruff、pytest、pre-commit 配置；
- Docker 构建中适配 workspace 安装和包目录挂载的逻辑。

不要恢复 `0.11.0` 的单包根目录布局，也不要把源码重新移动回根目录的 `homelab_airflow_dags/`。

迁入当前树后，应先建立一份 DevOps 基线差异，迁移结束时复核这些差异仅包含必要的 Airflow 版本替换：

```shell
git diff --stat origin/add-youtube-provider -- justfile cog.toml .github pyproject.toml .pre-commit-config.yaml .ruff.toml .yamlfmt.yaml mkdocs.yml docs README.md
```

其中 `justfile`、`cog.toml` 和 workflow 的结构性差异应为零。若存在差异，实施 Agent 必须逐项解释并缩小修改范围。

## 4. 依赖回退

### 4.1 主 DAG 包

修改 `packages/homelab-airflow-dags/pyproject.toml`：

- 固定 `apache-airflow==2.11.0`；
- 删除 Airflow 3 才需要的 `apache-airflow-providers-standard`；
- 删除仅因 Airflow 3 将 CeleryExecutor 拆包而加入的 `apache-airflow-providers-celery`；
- 保留 Amazon provider 和其他业务依赖；
- 检查 provider 版本是否声明支持 Airflow 2.11，若不支持则使用满足现有业务能力的最高兼容版本。

### 4.2 Bark 包

修改 `packages/homelab-airflow-bark/pyproject.toml`：

- 固定 `apache-airflow==2.11.0`；
- 保留 Pydantic 与 requests 依赖；
- 确保它与主 DAG 包使用完全一致的 Airflow pin，避免 workspace 解析出双版本冲突。

### 4.3 Provider 包

逐一检查 YouTube 和 Bilibili provider 的 `pyproject.toml`。如果它们不直接使用 Airflow API，不要为了形式统一增加 Airflow 依赖；如果后续加入 Hook、Operator 或 Connection，则将兼容范围明确限制到 Airflow 2.11。

### 4.4 锁文件

依赖文件修改完成后重新生成 `uv.lock`，不得手工编辑锁文件：

```shell
uv lock --index-strategy unsafe-best-match
```

私有索引 `homelab` 需要有效凭据。应通过本地环境变量提供 `UV_INDEX_HOMELAB_USERNAME` 和 `UV_INDEX_HOMELAB_PASSWORD`，不得写入仓库、命令输出或文档。若出现 401，应先修复本机凭据，再继续解析。

## 5. Python API 兼容迁移

Airflow 3 公共 SDK 在 Airflow 2.11 中不可用。至少处理以下映射：

| Airflow 3 写法 | Airflow 2.11 写法 |
| --- | --- |
| `from airflow.sdk import dag` | `from airflow.decorators import dag` |
| `from airflow.sdk import task` | `from airflow.decorators import task` |
| `from airflow.sdk import BaseOperator` | `from airflow.models import BaseOperator` |
| `from airflow.sdk import Context` | `from airflow.utils.context import Context` |
| `providers.standard...sensor_task` | `@task.sensor(...)` |
| `providers.standard...virtualenv_task` | `@task.virtualenv(...)` |

重点文件：

- `packages/homelab-airflow-dags/src/homelab_airflow_dags/common_tasks/exchange_calendars.py`；
- `packages/homelab-airflow-dags/src/homelab_airflow_dags/dags/ibkr_account_snapshot.py`；
- `packages/homelab-airflow-bark/src/homelab_airflow_bark/operators.py`。

完成后执行全仓搜索，结果应为空（历史 changelog 可酌情保留）：

```shell
rg -n "airflow\.sdk|airflow\.providers\.standard|3\.2\.0" .
```

不要只让导入测试通过；需要验证 DAG 装饰器、sensor、virtualenv task、Operator 模板字段及 Context 类型在 Airflow 2.11 下均能加载。

## 6. Dockerfile 回退

修改 `docker/Dockerfile`：

- 基础镜像改为 `apache/airflow:2.11.0-python3.12`；
- `AIRFLOW_VERSION` 默认值改为 `2.11.0`；
- 保留当前 workspace 的复制与 `uv pip install -e packages/homelab-airflow-dags`；
- 保留私有索引认证和 `unsafe-best-match` 策略；
- 保留当前源码包到 `/opt/airflow` 的可靠软链接方式；
- 删除仅描述 Airflow 3 的注释和假设。

构建完成后在镜像中验证：

```shell
airflow version
python -c "import homelab_airflow_dags"
python -c "import homelab_airflow_bark"
```

第一条必须输出 `2.11.0`。

## 7. Docker Compose 服务拓扑回退

以 `0.11.0:docker/docker-compose.yaml` 为 Airflow 2 服务模型参考，但保留当前 workspace 路径。必须完成：

- 用 `airflow-webserver`（`command: webserver`）替代 Airflow 3 的 `airflow-apiserver`；
- 删除独立的 `airflow-dag-processor` 服务；
- 删除 `AIRFLOW__CORE__AUTH_MANAGER`；
- 删除 `AIRFLOW__CORE__EXECUTION_API_SERVER_URL`；
- 删除 Airflow 3 API JWT 配置；
- 恢复 `AIRFLOW__API__AUTH_BACKENDS`；
- webserver 健康检查恢复为 `/health`；
- scheduler、worker、triggerer、flower 和 init 使用 `0.11.0` 的 Airflow 2 命令与依赖关系；
- Celery result backend 使用 Airflow 2.11 已验证的连接字符串；
- `_AIRFLOW_DB_MIGRATE` 和 `_AIRFLOW_WWW_USER_CREATE` 保持 Airflow 2 初始化方式；
- DAG volume 指向当前路径 `packages/homelab-airflow-dags/src/homelab_airflow_dags/dags`；
- logs 保持根目录 `logs/` 挂载；
- 不重新引入已被 workspace 取代的根目录 `dags/` 源码结构。

先运行 Compose 静态解析，再启动：

```shell
podman compose -f docker/docker-compose.yaml config
just podman-compose-up
```

启动后确认 webserver、scheduler、worker、triggerer 全部健康，并检查 DAG import errors 为零。

## 8. 测试与验收

### 8.1 静态与单元测试

```shell
just lint
just test
just test-all
just docs-build
git diff --check
```

若 `just test-all` 受本机 Python 版本限制，记录未执行版本及原因，但至少完成项目默认 Python 3.12 测试。

### 8.2 Airflow 验收

在 Airflow 2.11 环境执行：

```shell
airflow version
airflow dags list
airflow dags list-import-errors
airflow tasks list ibkr_account_snapshot
```

验收条件：

- Airflow 精确为 `2.11.0`；
- `ibkr_account_snapshot` 可解析；
- exchange calendar sensors 可实例化；
- Bark Operator 可导入和实例化；
- DAG import errors 为零；
- workspace 中所有包仍能独立构建；
- 文档和 CI 不再宣称运行于 Airflow 3.2.0。

### 8.3 容器验收

- 初始化数据库成功；
- 管理员用户可创建；
- webserver `/health` 正常；
- scheduler heartbeat 正常；
- Celery worker ping 正常；
- triggerer 正常；
- 重启一次 Compose 后状态仍稳定。

## 9. 建议提交序列

为便于审阅和回滚，建议拆分为：

1. `refactor: preserve workspace packages on airflow 2 baseline`
2. `fix: restore airflow 2.11 dependencies and imports`
3. `fix: restore airflow 2 docker stack`
4. `test: validate airflow 2 dag and operator compatibility`
5. `docs: document airflow 2.11 rollback`

每个提交前执行相关最小测试；最终提交前执行第 8 节的完整验证。

## 10. 风险与回滚

- Airflow 2.11 与某些最新版 provider 可能存在约束冲突：以 `uv lock` 解析结果和官方包元数据为准，降低 provider 版本时记录原因。
- Airflow 3 数据库不能假设可直接降级：本地开发数据库建议新建 volume；生产环境必须单独制定数据库备份、迁移和回滚方案，本计划不授权删除现有数据库 volume。
- Airflow 3 的序列化 DAG、认证配置和 API 客户端可能与 2.11 不兼容，需要逐项清理环境配置。
- 私有 PyPI 凭据缺失会阻止锁文件和镜像构建；不得用删除私有依赖的方式绕过。
- 若迁移失败，保留本分支失败现场，通过保护分支返回 `origin/add-youtube-provider`，不要改写已推送历史。

## 11. 完成定义

只有同时满足以下条件才能认为迁移完成：

- 当前 workspace、多包结构和业务代码均保留；
- 运行时和开发依赖均固定为 Airflow 2.11.0；
- 全仓不存在有效的 Airflow 3 API 或容器配置；
- 锁文件由工具成功生成；
- lint、测试、文档构建和 DAG import 检查通过；
- Airflow 2 Compose 栈实际启动并通过健康检查；
- 迁移说明记录所有不可执行的验证及其原因。
