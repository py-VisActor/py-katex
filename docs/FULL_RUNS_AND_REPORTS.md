# 核心静态迁移：日志与报告复用

本工作流不安装、构建、发布包。固定来源与分母见 `references/upstream.lock.json`、`full-core-inventory.json`。当前验收入口为 [FULL_STATIC_ACCEPTANCE.md](FULL_STATIC_ACCEPTANCE.md)；历史 alpha 记录保持原样。

在已具备依赖的环境下，从 py-katex 根目录执行：

```powershell
C:/venvs/pymmd-20261102/Scripts/python.exe tools/workflow.py batch --scope MATH-FULL --plan tools/plans/full-repair.json --keep-going
```

此计划依次保存两个仓库的源码和验证输入快照，运行锁定上游注册 oracle、核心功能输入采集、官方 A 图、新旧全部单元测试、功能输入及等价关系验证、CPU 静态图检查。`--keep-going` 用于保留首轮完整失败分布，失败组不算通过。核心语料采集不等于执行原 Jest 的全部 matcher、HTML/MathML 或 snapshot 断言。

取得成功的 unit run 后，修改 `tools/plans/full-matrix.json` 中固定 A 图来源到该 run，运行：

```powershell
C:/venvs/pymmd-20261102/Scripts/python.exe tools/workflow.py batch --scope MATH-FULL --plan tools/plans/full-matrix.json --keep-going
C:/venvs/pymmd-20261102/Scripts/python.exe tools/workflow.py batch --scope MATH-FULL --plan tools/plans/math-legacy-visual.json --keep-going
```

矩阵计划验证全部独立公式和真实 Mermaid 集成图的 CPU/auto/必需 GPU，以及 PNG/JPG/WebP/SVG/PDF 五种真实导出。历史计划保留 297 个流程图正例，以及源错误、负例、范围分类；曾归入数学排除的两个 ID 保留并明确提升为数学绘制断言。固定 A 仅在输入与原始图像指纹一致时复用，禁止重写或美化原图。

运行 `tools/report_full.py --unit <unit-run> --visual <matrix-run> --legacy <legacy-run> --manual-receipt <layout-review.json> --manual-receipt <canvas-review.json> --out <new-report-directory>` 生成报告；三个 run 必须全部成功、源码未变且联合候选与当前一致。人工回执也必须通过且对应同一联合候选，否则拒绝生成。生成器只读保存的图像与指标，报告不触发重新绘图。

所有命令应由 `workflow.py record` 或版本化 batch plan 执行，统一保存 argv、环境、stdout/stderr、输入和输出 SHA256、退出码及源码变化。已关闭的 run 不修改；修复后新建 run。`joint-source.zip` 保存产品源码，`joint-verification-inputs.zip` 保存当时测试、工具、文档与引用的完整字节，便于复现曾经失败的输入。

报告目录放在相邻 `py-mermaid/reports/<report-run-id>/`；使用已有 `127.0.0.1:8765` 服务，或启动 `py-mermaid/tools/serve_reports.py`。用记录命令执行 `node tools/qa_report.cjs --url <url> --out <new-qa-directory>`，逐一检查案例与三种后端，校验全部嵌入原图、五种下载、桌面/手机宽度和零外部请求。最后执行 `tools/full_delivery_audit.py --out <new-audit-directory>`，核对文档、闭合 run、HTTP 字节、联合源码并归档交付资料。

像素差只用于诊断；验收断言覆盖内容、结构、字体轴、数学几何、颜色、资源实际像素、溢出边界和真实后端。可见错误图保留诊断；源拒绝输入不得算作成功公式。已知 Mermaid 宿主差异必须在报告逐例标注。
