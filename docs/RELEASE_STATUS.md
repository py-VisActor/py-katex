# py-visactor-katex 0.1.0 已正式发布

2026-11-06：**PyPI 与 GitHub 正式发行均已完成，实际下载与安装复验通过。**

```shell
python -m pip install py-visactor-katex==0.1.0
```

Python 导入为 `py_katex`，控制台命令为 `py-katex`，源码仓库为 `py-VisActor/py-katex`。
需要 CPython 3.13，固定原生依赖 `py-skia-canvas==0.1.0a18`；已验证 Windows AMD64 和 Linux glibc 2.28+ x86_64。

- [PyPI 0.1.0](https://pypi.org/project/py-visactor-katex/0.1.0/)
- [GitHub 正式发行](https://github.com/py-VisActor/py-katex/releases/tag/py-visactor-katex-v0.1.0)
- [完整发布流水线](https://github.com/py-VisActor/py-katex/actions/runs/42139837741)
- [机器发行记录](../references/release-publication-0.1.0.json)

## 实际验证

本地构建的同一 wheel/sdist 上传 GitHub，下载核 SHA 后，在 Windows/Linux 干净环境分别安装；
所有平台步骤成功后，GitHub OIDC 上传原字节到 PyPI，不重建、不覆盖。实际 PyPI 文件再下载核 SHA，
在 Linux 以及本机 Windows 各自重新安装验证。Windows 的 CPU/auto/GPU、两种 CLI、五种导出通过；
Linux 验证 CPU。每组 wheel/sdist 的 CPU 图均逐个核对真实输出，三份 CI ZIP 共 78 个实际文件见证；
本机公开包两种安装各执行三后端共 78 个实际输出。

45 个数学运行文件（含 20 字体）与既有核心验收逐 SHA 对照，唯一运行源码变化为版本号
`0.1.0a0 -> 0.1.0`。发行名变更只影响分发元数据，不改变 `py_katex` 的代码、字体与原始度量。
既有 973 个方法等核心静态证据保持历史候选口径，不改称新发行重跑。

## 发行字节

| 文件 | SHA256 | bytes |
| --- | --- | --- |
| `py_visactor_katex-0.1.0-py3-none-any.whl` | `d4724ae0b65b2cec07c4e51e48863e90808add37bbcc336baf6e1d576da7b09d` | 445187 |
| `py_visactor_katex-0.1.0.tar.gz` | `a392b9fd4fe36f42e6845b59e47b04b898ec6cb02fb1beb20b8bc6ac2d19992d` | 745907 |

源码 tag 提交：`250c55bd3864d8c6615e79984f398341d03edc4e`；发行 manifest SHA256：`ce49d2f2663ddca492a5d7a5948a1549e70ed178f733f751e94d9f94d9e3248c`。

## 证据与复用

- 新名称构建：`test-runs/RELEASE-batch-20261106T004856Z-3d638003`
- GitHub 上传/下载：`test-runs/RELEASE-batch-20261106T005107Z-ed6ec48f`
- 实际 PyPI/Windows 安装：`test-runs/RELEASE-batch-20261106T005313Z-d2918e05`
- 完整交付归档：`test-runs/RELEASE-published-delivery-20261106T005617Z-c83b8ecf`

`tools/release_collect_ci.py` 下载并校验实际 CI ZIP、每张图片和发布状态；`tools/release_pypi.py` 核对实际 PyPI 元数据与文件；`tools/release_artifacts.py` 验证 payload 并执行隔离安装。命令使用统一 `tools/workflow.py` 记录。

## 名称变更与历史

PyPI 曾拒绝 `py-katex` 相似名，因此正式发行采用 `py-visactor-katex`。原 `v0.1.0` 及旧名资产保留为被拒名称的历史候选，未覆盖；正式 tag 是 `py-visactor-katex-v0.1.0`。旧失败/待授权状态见 [历史记录](releases/0.1.0-rejected-py-katex.md)。

数学范围仍限固定 KaTeX 核心静态能力，独立 contrib（包括 mhchem）、任意宿主 CSS 和 HTML/MathML 输出不在该范围；详见 [核心静态验收](FULL_STATIC_ACCEPTANCE.md)。
