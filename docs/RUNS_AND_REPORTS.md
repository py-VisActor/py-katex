> 2026-11-06 **固定 KaTeX 0.18.11 核心静态迁移已完成本地验收**：973 方法、684 上下文、1909 功能输入/217 等价关系、275 案例三后端与 297 历史流程图三后端通过。当前入口为 [完整验收](FULL_STATIC_ACCEPTANCE.md)。安装验证暂缓，未提交推送发布；下方旧 alpha/未实现状态仅作历史。

# 数学模块日志与报告复用

工作目录 `C:/code/py-visactor/py-katex`；当前解释器 `C:/venvs/pymmd-20261102/Scripts/python.exe`。不执行安装验证。开发测试通过命令计划的环境字段把本仓库与相邻 Mermaid 的 `src` 加入 PYTHONPATH；生产依赖不得用路径注入回退。

```powershell
C:/venvs/pymmd-20261102/Scripts/python.exe tools/workflow.py batch --plan tools/plans/math-unit.json --keep-going
C:/venvs/pymmd-20261102/Scripts/python.exe tools/workflow.py batch --plan tools/plans/math-visual.json --keep-going
C:/venvs/pymmd-20261102/Scripts/python.exe tools/workflow.py batch --plan tools/plans/math-legacy-visual.json --keep-going
C:/venvs/pymmd-20261102/Scripts/python.exe tools/workflow.py batch --plan tools/plans/math-report-rebuild.json
C:/venvs/pymmd-20261102/Scripts/python.exe tools/workflow.py batch --plan tools/plans/math-report-qa.json
C:/venvs/pymmd-20261102/Scripts/python.exe tools/workflow.py verify --run test-runs/MATH-batch-20261105T122948Z-8bf16e51
```

`record` 封装单命令，`batch` 按 argv 数组执行计划，`verify` 核验已封存 run。共享 `py-mermaid-run/v1` 结构：run.json、events.ndjson、commands/*/command.json/result.json、原始 stdout/stderr、artifacts 指纹；状态由真实退出码确定。占位符为 `{repo}`、`{run}`、`{runid}`、`{python}`。开始和结束检查产品源身份；`joint_candidate.py` 同时冻结两个仓库，避免只检查一个仓库。

上述报告计划引用的是本轮具体 run。新候选必须更新计划中 unit/visual/legacy/export 输入路径和 QA URL，不能把旧 B 图改名成新证据。A 图只有在固定官方版本、输入 fixture 与原图 SHA 均相符时才可复用；`capture_math.cjs`/现有 Mermaid oracle 用于重新采集官方 A，开发 oracle 的浏览器依赖来自本机既有环境，不是生产依赖。B 必须真实调用公开 Python API，再检查实际像素、字符/线/路径与几何；像素差只作诊断，不掩盖缺失或裁切。

`report_math.py` 仅接收同一联合候选的成功记录，核对案例分母及图片/导出指纹，再内嵌原始 A/B；报告生成不重新绘图、不安装软件。`qa_report.cjs` 遍历所有案例×后端并验证下载内容、页面布局和网络请求。报告服务复用相邻 Mermaid 的 8765 端口；需要重启时使用 `../py-mermaid/tools/serve_reports.py`（先查看该工具 --help）。

封存 run 不可添加、删除、改写任何文件，包括派生联系表；新审计/截图必须新建 run。首轮失败不覆盖。手工 QA 回执引用实际查看的原图和源身份，源缺陷与宿主差异分别列出。

当前报告：http://127.0.0.1:8765/MATH-batch-20261105T122804Z-878bf5d4/index.html

最终证据目录：
- unit: `test-runs/MATH-batch-20261105T121812Z-f140829a`
- visual: `test-runs/MATH-batch-20261105T121812Z-73861ed7`
- legacy: `test-runs/MATH-batch-20261105T121812Z-85def7ba`
- exports: `test-runs/MATH-batch-20261105T122453Z-26698b8b`
- report: `test-runs/MATH-batch-20261105T122804Z-878bf5d4`
- htmlQa: `test-runs/MATH-batch-20261105T122948Z-8bf16e51`
