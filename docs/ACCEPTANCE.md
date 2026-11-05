> 2026-11-06 **固定 KaTeX 0.18.11 核心静态迁移已完成本地验收**：973 方法、684 上下文、1909 功能输入/217 等价关系、275 案例三后端与 297 历史流程图三后端通过。当前入口为 [完整验收](FULL_STATIC_ACCEPTANCE.md)。安装验证暂缓，未提交推送发布；下方旧 alpha/未实现状态仅作历史。

# py-katex 本地验收（2026-11-05）

已在 `C:/code/py-visactor/py-katex` 完成 Python 数学解析、TeX 盒模型排版、Canvas 原生静态绘制，并接入相邻 `py-mermaid` 的流程图标签。远端仓库原已存在，本轮克隆并实现本地源码；版本 `0.1.0a0`，尚未提交、推送或发布。本记录验收原生静态 alpha 范围，不声明完整 KaTeX 兼容。

## 能力与接口

公开 `parse`、`layout`、`typeset`、`draw`、`render` 与 CLI；支持分数、根式、上下标、积分/求和及 limits、伸缩括号、重音与伸缩箭头、矩阵/array/cases/aligned、数学字体/颜色/文本、作用域宏、规则线、phantom/smash/lap/盒子等功能族。实际命令、语义分支和拒绝项以 `references/parser-sources.json`、`function-inventory.json` 与源测试为准，功能族名称不表示全部组合已经兼容。

运行时是 Python AST → TeX boxes → glyph/rule/path → `py-skia-canvas==0.1.0a18`；不调用 Node、浏览器或 JS。20 份上游 TTF 随包提供，使用源字体度量；离线生成 PNG/JPG/WebP/SVG/PDF。固定源 KaTeX `0.18.11` / `d5bed9f38a8d747b9c4a12e18897a514707e1c26`，MIT 声明及逐文件指纹保存在 `references/upstream.lock.json` 和第三方许可中。

Mermaid `htmlLabels=true` 的节点、边和分组标签支持 `$$...$$` 及文本混排，使用原生公式盒测量和绘制。`htmlLabels=false` 依照固定源行为保留字面公式；配置名不意味着生产运行时使用 DOM。保护公式后再做 Markdown/HTML 清洗，保留 TeX 反斜杠、`<`、`&` 和矩阵分行。

## 实际验证

- 同候选 712 个测试方法通过：676 产品、36 工具；含历史 486 个方法与新增数学/集成方法。
- 61 个独立公式、8 张流程图，CPU/auto/GPU 共 207 个视图通过；每种后端另验 7 个数学负例。
- 历史 F01.1/F01.2/F01.3/F01.4 共 297 个正例 × 3 后端通过，保留原负例、源缺陷与范围排除分母。两个历史延后数学案例显式提升为真实公式绘制断言，并未删除跳过。
- 五种格式均产生真实文件；HTML 的 207 个视图、五个下载、桌面/移动布局、零外部请求通过自动 QA；布局与集成人工检查已记录原图路径。

[打开 HTML 对比报告](http://127.0.0.1:8765/MATH-batch-20261105T122804Z-878bf5d4/index.html)。HTML SHA256：`9f7ef845b1a8f495d66824f48208da6206f6b3235d3b9e3f5b7a20bf493e88ee`。证据和各组方法数见 [verification-summary.json](../references/verification-summary.json)。

最终数学源码 SHA256：`6e11f0a8f9f88c78fb387faf4429cfea72781a4e961328bf53299625bea2cb80`；Mermaid：`6e37306deb59a5eb21a2bcceedd66c128a2367f392b094854e2e9bdb3e0e4088`。完整源快照为 `test-runs/MATH-batch-20261105T121812Z-73861ed7/artifacts/joint-source.zip`。测试、报告与原图使用同一联合候选，文档收口未改变产品源码。

## 明确差异与边界

- `math-flow-metadata`：官方 Mermaid 元数据预处理将反斜杠 n 破坏为换行，A 图显示残缺的字面公式；本实现保留 TeX 并绘制 ν<y，属于明确修正源异常，不能声称与该异常图相同。

- `math-flow-group`：官方 MathML 宿主显示斜体 Unicode Group；原生 TeX 使用 Main-Bold 正体粗体。

- `math-flow-mixed`：官方 flex/MathML 合并公式边界空格；原生保留 Area πr² units 的边界空格。

- 不是完整 KaTeX 兼容实现；注册项与功能族映射不等于逐分支覆盖率。
- 自动公式编号/tag、CD、部分宏展开边界尚未实现；明确拒绝未支持语法。
- Parser 不暴露 displayMode/strict/leqno/fleqn 全部源选项；Options.display_mode 用于视觉样式。
- HTML class/id/style/data、includegraphics 拒绝；href/url 仅保留静态文本，无交互。
- 部分 Unicode 缺少源字体度量时明确报错，不用系统字体伪造数学度量。
- pmb 保留偏移副本，未复刻原实现 0.04px 模糊。
- 本轮验证 Windows 本地环境；安装、构建、Linux/no-loader 验证未执行。
- 版本 0.1.0a0 未发布；Mermaid 声明依赖版本，开发验证使用两个源码目录 PYTHONPATH，安装解析需后续发布或本地安装阶段验证。

17 个未支持注册名称及 3 个动态宏的清单保留在机器摘要与源映射中；334 个注册名不是覆盖率。未支持输入必须抛出明确错误，不返回空图或把普通字符串当作成功公式。

## 过程与交接

P0 来源与接口 → P1 源码 → P2 源断言 → P3 首次失败与批量修复 → P4 同候选验证及原图 QA → P5 文档本地交付已完成。首轮失败、后续修复、错误的早期报告、最终报告均保留独立日志。下一阶段应针对清单补足命令和边界，再独立验证发布/安装；不将其它 Mermaid 图种自动视为已验收。标准命令见 [RUNS_AND_REPORTS.md](RUNS_AND_REPORTS.md)。
