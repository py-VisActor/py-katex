# py-visactor-katex 0.1.0 发行状态

2026-11-06：PyPI 拒绝原发行名 `py-katex`，返回
`This project name is too similar to an existing project`。
当前发行名改为 **`py-visactor-katex`**，与组织已有 `py-visactor-elk` 命名一致。
Python 导入名仍为 `py_katex`，控制台命令仍为 `py-katex`，GitHub 仓库仍为 `py-VisActor/py-katex`。

```shell
python -m pip install py-visactor-katex==0.1.0
```

当前阶段：重新构建新发行名的 wheel/sdist，并重新验证安装。**尚未声明 PyPI 已发布或新名已获准注册。**
PyPI 查询 404 不代表名称可以注册；最终以账户侧 Pending Publisher 注册和真实上传结果为准。

## 候选与历史

新候选 tag 为 `py-visactor-katex-v0.1.0`。原 `v0.1.0` 及其旧名资产保留为名称被拒的历史，
不能用于新名发布，不覆盖旧资产、日志或验证结果。旧状态见
[被拒名称的发行记录](releases/0.1.0-rejected-py-katex.md)，命名决策见
[机器记录](../references/pypi-name-decision.json)。

数学运行文件沿用已验收实现，版本仍为 `0.1.0`；与历史核心候选相比仅版本常量变化，
发行名变更不会改变数学源码、字体或度量。原始 973 方法等核心验收保持原候选口径。

## 发布流程

使用 `tools/plans/release-namespaced-build.json` 构建；严格检查元数据、45 个运行文件和 20 字体，
对新 wheel/sdist 在仓库外、空 PATH、Python `-I` 下实际安装并执行 CPU/auto/GPU、五格式和 CLI。
GitHub 上传本地已验收的原始文件。双平台 CI 下载同一组文件，在 Windows/Linux 重新验证
wheel/sdist；两平台均成功后才尝试 OIDC 上传。上传后下载 PyPI 文件核 SHA、安装复验，
最后提升新候选 GitHub Release 为正式版。

PyPI Pending Publisher 必须使用：

| 字段 | 值 |
| --- | --- |
| Project name | `py-visactor-katex` |
| GitHub owner | `py-VisActor` |
| Repository | `py-katex` |
| Workflow | `publish-pypi.yml` |
| Environment | `pypi` |

只改变 Pending Publisher 的项目名，其余字段保持。账户入口：
[PyPI Publishing](https://pypi.org/manage/account/publishing/)。不需要在聊天、代码或日志中提供 token。

## 新发行名本地验收

运行 `test-runs/RELEASE-batch-20261106T004856Z-3d638003` 已成功闭合且源码未变。45 个运行文件与已验收数学实现对照通过，wheel/sdist 两个干净外部环境各执行 CPU/auto/GPU、13 个实际输出、两种 CLI；严格元数据及 16 个受影响 API 方法通过。

- `py_visactor_katex-0.1.0-py3-none-any.whl`：SHA256 `d4724ae0b65b2cec07c4e51e48863e90808add37bbcc336baf6e1d576da7b09d`，445187 bytes。
- `py_visactor_katex-0.1.0.tar.gz`：SHA256 `a392b9fd4fe36f42e6845b59e47b04b898ec6cb02fb1beb20b8bc6ac2d19992d`，745907 bytes。
