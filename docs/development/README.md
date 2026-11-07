# 维护者与 AI agent 文档

用户安装和 API 见[用户目录](../README.md)。修改前先读根目录 [AGENTS.md](../../AGENTS.md)，检查 `git status`，保留现有修改。

## 代码与协作

- [开发工作指南](WORKFLOW.md)：任务阅读、实现约束、独立验证与完成条件。
- [接口合同](../INTERFACES.md) · [数学 AST](../AST.md)
- `src/py_katex/`：解析、宏、排版、Canvas；`tests/`：独立来源断言；`references/`：来源清单与许可证。
- 多人并行时按[共享协作规范](../../../py-mermaid/docs/PARALLEL_EXECUTION.md)分配单文件 owner；接口变更先协调。

## 开发与检查

在受支持的 CPython 3.13 环境中，从本仓库开发安装：

```sh
python -m pip install -e .
python -m unittest discover -s tests
```

安装、下载、构建、提交或发布须遵守当前任务授权；以上是维护者命令说明，不代表自动执行授权。
原版 JS 只供独立开发 oracle，不能成为生产运行依赖。预期来自锁定 KaTeX 源码，不能从当前 Python 输出反推。

## 固定来源与历史索引

固定 KaTeX 0.18.11 / `d5bed9f38a8d747b9c4a12e18897a514707e1c26`。
下列资料保留原始候选、阶段与失败，不是用户操作指南，也不表示新候选自动继承通过。

| 分类 | 资料 |
| --- | --- |
| 原始计划与状态 | [执行计划](../EXECUTION_PLAN.md)、[完整静态迁移计划](../FULL_STATIC_MIGRATION.md)、[历史状态 JSON](../execution-state.json) |
| 旧 agent 入口 | [迁移前原文快照](archive/AGENTS-2026-11-07.txt)，保留字节；不是当前指令 |
| 验证与证据 | [早期验收](../ACCEPTANCE.md)、[完整静态验收](../FULL_STATIC_ACCEPTANCE.md)、[运行与报告](../RUNS_AND_REPORTS.md)、[完整运行索引](../FULL_RUNS_AND_REPORTS.md) |
| 发行 | [发行状态](../RELEASE_STATUS.md)、[发行说明目录](../releases/)、[变更记录目录](../changes/)、[Changelog](../../CHANGELOG.md) |
| 当前维护发行 | [0.1.1 说明](../releases/0.1.1.md)；此前发行状态仍保留原始版本口径 |
| 归属 | [第三方声明](../../THIRD_PARTY_NOTICES.md)、`references/licenses/` |

`test-runs/` 是开发证据输出；已有闭合运行、原图、失败日志和 manifest 不覆盖。README/PyPI 首页不承担运行台账职责。
## 文档分类索引

[逐文件受众清单](documentation-inventory.json)区分用户、开发、历史、证据与许可资料。旧路径保留来源上下文；清单不把旧验收提升为当前功能结论。
