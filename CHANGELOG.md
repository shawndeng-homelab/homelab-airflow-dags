# Changelog
All notable changes to this project will be documented in this file. See [conventional commits](https://www.conventionalcommits.org/) for commit guidelines.

- - -
## [0.12.0](https://github.com/shawndeng-homelab/homelab-airflow-dags/compare/ed53cb903bdaaaeb53d7a57f159112d4125e7c93..0.12.0) - 2026-08-13
### Package updates
- [homelab-airflow-dags](packages/homelab-airflow-dags) bumped to [homelab-airflow-dags-0.1.0](https://github.com/shawndeng-homelab/homelab-airflow-dags/compare/9000549eeee3b79ed0efd540353b86ba0c073b3b..homelab-airflow-dags-0.1.0)
### Global changes
#### Bug Fixes
- use `podman compose` instead of `podman-compose` in justfile - ([704ae4b](https://github.com/shawndeng-homelab/homelab-airflow-dags/commit/704ae4bc8276b4e1759bf5f6c7bb750e86063ff8)) - colyerdeng
- make import test pass under Airflow 3; refresh uv.lock - ([05c5d87](https://github.com/shawndeng-homelab/homelab-airflow-dags/commit/05c5d87a52caf480308099a4f2ab2161455b69c9)) - colyerdeng
- resolve docker-compose volume paths relative to repo root - ([cf288e3](https://github.com/shawndeng-homelab/homelab-airflow-dags/commit/cf288e31469a7d2c4206e3d113ccc7dfbe2cc009)) - colyerdeng
- create logs/ before podman compose up - ([549b920](https://github.com/shawndeng-homelab/homelab-airflow-dags/commit/549b920b81d6213e89494f66153e3db9b1f7fae1)) - colyerdeng
- ensure logs/ exists via .gitkeep (avoid shebang/cygpath on Windows) - ([252eef2](https://github.com/shawndeng-homelab/homelab-airflow-dags/commit/252eef2e8ed83248135f84a147218c9cca39f474)) - colyerdeng
- enable FAB auth manager + correct api-server healthcheck (Airflow 3) - ([390f43c](https://github.com/shawndeng-homelab/homelab-airflow-dags/commit/390f43c899d487684c6de61749ef61f5221b7393)) - colyerdeng
- force AIRFLOW_HOME=/opt/airflow in containers (DAGs not found) - ([0c53ee4](https://github.com/shawndeng-homelab/homelab-airflow-dags/commit/0c53ee47af3893bdfb00d10e660a8975a2de2662)) - colyerdeng
- add cocogitto changelog separator so cog bump can update CHANGELOG - ([ed53cb9](https://github.com/shawndeng-homelab/homelab-airflow-dags/commit/ed53cb903bdaaaeb53d7a57f159112d4125e7c93)) - colyerdeng
#### Continuous Integration
- unblock cocogitto check (allow dockerfile type, scope to latest tag) - ([ff31d7c](https://github.com/shawndeng-homelab/homelab-airflow-dags/commit/ff31d7c962f8baafebeefc5f415b5d520be556ed)) - colyerdeng
#### Features
- upgrade to Airflow 3.2.0 and restructure as uv workspace - ([de0d91e](https://github.com/shawndeng-homelab/homelab-airflow-dags/commit/de0d91e86cf134ea2870cd7ee06be97381b3f708)) - colyerdeng
- update - ([123a62a](https://github.com/shawndeng-homelab/homelab-airflow-dags/commit/123a62ac6bedd183d1196a538fec010b7cbbb4ef)) - colyerdeng
#### Miscellaneous Chores
- update compsoe file - ([e63f50c](https://github.com/shawndeng-homelab/homelab-airflow-dags/commit/e63f50cd4d96e17aa44af4091df9bf49fb85d2b7)) - colyerdeng
#### Refactoring
- base docker-compose on official Airflow 3 (add dag-processor, apiserver) - ([ec2eb31](https://github.com/shawndeng-homelab/homelab-airflow-dags/commit/ec2eb3191710a5a5f7aaf6ad29948d65ead0c49d)) - colyerdeng
- mount the whole package, point DAGS_FOLDER at its dags subdir - ([1b9e051](https://github.com/shawndeng-homelab/homelab-airflow-dags/commit/1b9e0512d290adbe17ca983a19fa7ccb80befcfa)) - colyerdeng
#### Style
- lint code - ([1171ec6](https://github.com/shawndeng-homelab/homelab-airflow-dags/commit/1171ec674d057efcfdbc9a38b1935ab2b7433d3e)) - colyerdeng

- - -

## 0.11.0 (2026-01-24)

### Feat

- add exchange-calendars

## 0.10.2 (2025-11-12)

### Fix

- fix dag timezone and rm depends

## 0.10.1 (2025-11-10)

### Fix

- fix docker miss git and account list
- fix docker miss git and account list
- fix docker miss git and account list

## 0.10.0 (2025-11-06)

### Feat

- add ibkr account values snapshot
- add account snapshot dag
- add account snapshot dag

## 0.9.0 (2025-08-02)

### Feat

- rm dag

## 0.8.0 (2025-08-02)

### Feat

- update config moudle

## 0.7.1 (2025-07-22)

## 0.7.0 (2025-07-20)

### Feat

- update risk_management_task and update oss upload tools
- add new func
- add oss upload tools

## 0.6.0 (2025-07-19)

### Feat

- add risk dag and common tasks

## 0.5.4 (2025-07-18)

### Fix

- update

## 0.5.3 (2025-07-18)

### Fix

- update dockerfile build error with dcc

## 0.5.2 (2025-07-18)

### Fix

- update docker file build

## 0.5.1 (2025-07-18)

### Fix

- update test code
- rebuild pod

## 0.5.0 (2025-07-18)

### Feat

- add config func

## 0.4.0 (2025-07-11)

### Feat

- updaete lint

## 0.3.3 (2025-06-22)

### Fix

- fix github aciton for docker build

## 0.3.2 (2025-06-22)

### Fix

- udpate image info

## 0.3.1 (2025-05-29)

### Fix

- fix dag load and fix docs build

## 0.3.0 (2025-05-28)

### Feat

- add new test dag

## 0.2.1 (2025-05-28)

### Fix

- fix github action

## 0.2.0 (2025-05-28)

### Feat

- init project
