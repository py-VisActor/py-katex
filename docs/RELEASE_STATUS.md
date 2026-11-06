> 当前：**Windows/Linux wheel + sdist 安装验证通过，PyPI 尚未发布**。流水线 [42133486490](https://github.com/py-VisActor/py-katex/actions/runs/42133486490) 两个平台验证成功；上传步骤返回 `invalid-publisher`，需要 PyPI 账户添加项目专用 Pending Publisher。GitHub [v0.1.0 候选资产](https://github.com/py-VisActor/py-katex/releases/tag/v0.1.0) 已上传并独立下载核 SHA，保持 prerelease，待 PyPI 实际发布及下载复验后提升为正式版。

# 0.1.0 正式发行

2026-11-06 用户授权独立 py-katex 正式发布，包含必要的构建、安装验证、GitHub
提交/推送/发行和 PyPI 上传。此任务覆盖历史“安装验证暂缓、未授权发布”的限制。

当前阶段：已完成发行候选的 Windows wheel/sdist 仓库外安装、CPU/auto/GPU 实际绘制、
五格式导出、模块/控制台 CLI、严格 PyPI 元数据和受影响的 API 测试；尚待最终发行文件冻结、
GitHub Actions 双平台验证和 PyPI 实际上传/下载确认。**本页不声明 PyPI 已发布。**

安装目标：

```shell
python -m pip install py-katex==0.1.0
```

发行内容为一个 `py3-none-any` wheel 和一个 sdist，Python 要求为 `>=3.13,<3.14`，
固定依赖 `py-skia-canvas==0.1.0a18`。数学运行文件与原已验收候选逐 SHA 相同，
唯一运行源码变化是 `__version__` 从 `0.1.0a0` 改为 `0.1.0`；新增版本元数据、公开
README/CHANGELOG、控制台入口和发行工具。原 973 方法等证据保留原候选，不重标为发行测试。

第一组发行候选验证：`test-runs/RELEASE-batch-20261105T234942Z-d4ad2ab1`。
最终文件会另行冻结，记录实际 SHA256，不能使用旧候选字节冒充新构建。

## 发行流程

1. `tools/plans/release-build.json`：隔离构建、严格元数据、完整 payload 对照、仓库外
   wheel/sdist 安装与 CPU/auto/GPU、模块及控制台 CLI、受影响 API 检查。
2. `tools/release_github.py create`：仅上传已核验文件，保留 SHA256 清单；既有文件不覆盖。
3. `.github/workflows/publish-pypi.yml`：以 `workflow_dispatch` 输入精确 tag 和 manifest SHA，
   下载原始发行字节，在 Windows/Linux CPython 3.13 的干净环境验证 wheel/sdist/CPU；不重建发行物。
4. 只有两平台验证均成功，`pypi` 环境使用项目专用 GitHub OIDC Trusted Publisher 上传原字节。
5. 实际下载 PyPI 文件，核对元数据和逐文件 SHA，再安装复验；成功后将 GitHub 候选发行提升为正式版。

首次 PyPI 项目若尚无发布授权，应在 PyPI 账户 Publishing 页面添加 pending publisher：
项目 `py-katex`、GitHub owner `py-VisActor`、repository `py-katex`、workflow
`publish-pypi.yml`、environment `pypi`。不需要把 PyPI token 写入代码、日志或 GitHub secrets。

历史数学兼容范围、宿主差异与独立 contrib 分类见
[核心静态验收](FULL_STATIC_ACCEPTANCE.md)。安装验证授权的变化不扩展数学兼容承诺。

## 已冻结候选

最终 Windows 验证：`test-runs/RELEASE-batch-20261105T235223Z-5b497c88`。45 个运行文件（含 20 字体）核 SHA；wheel/sdist 两个干净外部环境各执行 CPU/auto/GPU 13 个实际输出，共 78 份；另有错误/状态/资源检查、两种 CLI、16 个受影响 API 方法及 `twine check --strict`。

- `py_katex-0.1.0-py3-none-any.whl` SHA256 `f13c78306cfb5bc89028fe05cdaf2c925c340c0bdce9f47525ccceab3b0cd684`，444990 bytes。
- `py_katex-0.1.0.tar.gz` SHA256 `69d4e0cfb9791b1557144881123819a49ce8c64688d93bb706582854a2cf17cc`，742235 bytes。

当前源码差异与文件分母见 [发行候选](../references/release-candidate-0.1.0.json)。GitHub/PyPI 仍以实际流水线结果为准。

## 双平台实际发行证据

[CI 机器记录](../references/release-ci-0.1.0.json)保存两平台 artifact ID、ZIP SHA、逐包 SHA、各 2 个外部安装及 26 个实际 CPU 输出。已下载 ZIP 并逐一核对全部输出文件 SHA，Node 不在 PATH，Python 使用 `-I`。未重建或覆盖已冻结 wheel/sdist。

## 恢复发布

在 PyPI [Publishing](https://pypi.org/manage/account/publishing/) 添加 Pending Publisher：project `py-katex`，owner `py-VisActor`，repository `py-katex`，workflow `publish-pypi.yml`，environment `pypi`。完成后仅重跑流水线 `42133486490` 的失败任务；双平台通过步骤无需重跑。上传后会核对实际 PyPI 字节并安装，最后提升 GitHub Release。
