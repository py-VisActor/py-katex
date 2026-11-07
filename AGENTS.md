# py-katex：AI agent 工作规范

## 1. 适用范围与职责

本文件适用于本仓库。当前用户任务优先于历史计划和状态说明。
发行名 `py-visactor-katex`，导入 `py_katex`，CLI `py-katex`。
负责数学解析、排版、离线字体和静态绘制；不要擅自扩大为浏览器或 LaTeX 文档宿主。
完整工作规程见[开发指南](docs/development/WORKFLOW.md)。

## 2. 开始工作

先运行 `git status --short`，辨认并保留用户及其他 owner 的修改。
按任务读取[开发索引](docs/development/README.md)及相关源码、接口和来源记录。
用户用法查 [docs/README.md](docs/README.md)，接口任务再读 `docs/INTERFACES.md` 和 `docs/AST.md`。
版本读取 `pyproject.toml`；任务阶段读取当前指令及其指定状态文件/运行记录。
`docs/execution-state.json` 和旧验收只描述记录时的状态，不自动恢复旧任务或授权。
跨仓/多人任务先明确文件 owner；需要变更公共模型或 API 时先协调。

## 3. 仓库地图

- `src/py_katex/`：公开 API、解析、宏、排版和 Canvas 绘制。
- `src/py_katex/data/`：数学字体、度量和固定源数据。
- `tests/`：功能、来源独立断言及绘制控制。
- `references/`：来源映射、许可证和机器记录。
- `docs/README.md`：用户目录；`docs/development/`：维护者/agent 目录。
- `tools/`、`test-runs/`：开发工具和不可覆盖的闭合运行证据。

## 4. 常用命令

在仓库根目录、受支持的 CPython 环境执行；依赖声明以 `pyproject.toml` 为准。
先复用已有环境；任务确需开发安装时使用：

```sh
python -m pip install -e .
```

文档改动检查本地链接、示例语法、API 与元数据，不因此构建或发布。
实现改动先编译并运行相关组；下列只是命令示例，不是所有任务都要全跑：

```sh
python -m compileall -q src/py_katex
python -m unittest discover -s tests -p test_api.py
python -m unittest discover -s tests
```

最后一条为全量单测；来源 oracle、三后端和图像矩阵按当前验证计划单独运行。
执行前核对 Python/依赖环境，不能用工作区路径回退冒充发行安装成功。

## 5. 修改约束

生产只使用公开 `py-skia-canvas` API，不引入 Node、浏览器、JS/DOM、skia-python 或 `.local` 依赖。
固定来源 KaTeX 0.18.11；源提交和文件哈希以版本控制来源记录为准。
字体、度量和移植算法保留来源与许可证；新增外部材料先核归属。
Canvas、Context 和字体对象留在创建线程，跨线程只传纯值或 bytes。
未知或未支持语法明确诊断，不用普通字符串、空图或吞错回退冒充成功。
公开 API/纯值合同变更说明兼容影响，不抢写其他 owner 文件。
测试预期独立取源；不能从当前 Python 输出反推正确结果或放宽标准掩盖缺陷。
不重置脏树、不覆盖原始基准和闭合运行；遇到用户修改先辨明关系。

## 6. 验证与完成条件

按当前任务区分文档、源码、独立测试、首跑修复和同候选验证阶段。
记录实际命令、环境、来源/候选哈希、退出码和失败；未执行的检查明确写出。
修复保留首轮失败，相关组通过后再做必要的共享消费者或全量回归。
绘制变化核真实原图、文字、关系、边界和可读性，不只看 trace 或测试数量。
完成报告说明改动、验证及剩余限制；历史通过不等于新候选全部兼容。
公共 README/PyPI 首页只放安装、用法、边界；迁移和证据通过开发索引保留。
按任务需要自主完成可逆的本地准备和检查；不要为纯文档任务额外安装、构建或跑绘图矩阵。
提交、推送和发布依据当前用户授权；不要由历史发行记录推导新的发布权限，也不重复请求已有授权。
