> 2026-11-06 **固定 KaTeX 0.18.11 核心静态迁移已完成本地验收**：973 方法、684 上下文、1909 功能输入/217 等价关系、275 案例三后端与 297 历史流程图三后端通过。当前入口为 [完整验收](FULL_STATIC_ACCEPTANCE.md)。安装验证暂缓，未提交推送发布；下方旧 alpha/未实现状态仅作历史。

# KaTeX 剩余静态迁移一次收口

2026-11-05 用户要求一次完成剩余工作。起点是本地 alpha（固定 KaTeX 0.18.11 / d5bed9f38a8d747b9c4a12e18897a514707e1c26），不是重写或重装。已有代码、失败日志、原图与报告全部保留。

## 本次目标

完成固定核心库的全部保留静态解析、宏、环境、排版、资源、配置、错误、字体与导出分支，并接入 Mermaid。范围分母包括全部核心 function/environment/macro 注册、Settings 选项、上游核心 spec 与 screenshotter 案例；不能用注册映射冒充验证。CD、公式编号/tag、futurelet/展开边界、模式/严格策略、图片及 HTML 静态样式均在本次完成范围。

DOM/MathML/HTML 输出后端、浏览器事件、链接激活、任意宿主 CSS 引擎不移植；对应输入的解析、安全、可见样式和诊断需要原生适配或明确记录宿主范围排除，不能静默丢视觉内容。独立 contrib 插件不属于核心注册分母（真实源345，旧扫描334）；auto-render/copy-tex/mathtex-script DOM集成、a11y及mhchem独立扩展在总清单分类保留，不将其称作核心命令兼容通过。

不运行 Node/浏览器/JS 作为生产实现；开发独立 oracle 可用已锁定 JS。只调用公开 Canvas API。图片仅显式注入的不可变离线资源或 data URI，不从公式自动访问网络/任意文件。安装/构建验证仍按用户要求暂缓；不自动提交、推送、发布。

## 协作与执行

- root：纯数据模型、完整Settings/API/CLI合同、核心分母汇总、源spec迁移工具、集成注册、日志与HTML报告、总验收。
- A(parser_config)：parser/macros/mode语义、环境与静态AST、完整来源映射；后续独立源测试。
- B(geometry_elk)：全部纯排版、CD/tag/编号/断行/尺寸/字体与数组组合；后续源数值与像素关系测试。
- C(canvas_labels)：离线图片、HTML静态适配、Canvas字体/绘制/导出、Mermaid数学接入；后续真实图片/资源与导出验证。

P0 保存起点与完整范围/接口；P1 集中补齐源代码，仅机械检查；P2 从固定上游建立完整命令/选项/spec/screenshotter分母与可执行独立测试；P3 同一源码保存首轮全部分组失败，再批量修根因；P4 冻结同一候选，全部单元/来源语料/历史流程图与CPU/auto/GPU真实绘制、人工QA与HTML报告；P5 写实际验收及完整差异清单。未验/失败不能计入通过；不能因明确抛未支持错误就认定剩余源码完成。

## 扩展合同

Options追加源Settings的原生对应项（strict/trust支持显式Python回调），max_expand允许非负数/Infinity（含小数阈值，负数按源钳0）但其它深度/节点预算独立。globalGroup通过显式MacroState可传递宏定义，默认请求隔离不变。content_width是静态容器像素宽，equation_counter是无宿主时的显式公式编号起点。

资源用ImageResource/ResourceBundle，绘图命令新增ImageCommand与含仿射矩阵/透明度/裁切的CommandGroup；均是纯值，不跨线程传递Canvas对象。MathBox.diagnostics记录可见错误/拒绝输出，不把noThrow错误当成功公式。新的AST细节以AST.md及worker回执为准，公共模型由root唯一修改。

## 验收出口

必须交付完整保留/排除分母、每个未通过项的实际原因、来源测试迁移与原始失败、同候选最终报告及可访问URL。功能完成与包发布/安装验证分开，不使用旧alpha报告证明新候选。

## P0 分母修正

通过锁定TS源码的真实声明注册（仅import机械检查，无公式执行），发现旧静态names数组扫描漏掉sizing.ts用Object.keys生成的11项。最终核心分母为312个函数+33个环境=345个注册名；宏表实际339（319字面+20动态），其中4个字面宏来自function/environment文件。旧334/315清单保留为历史，最终不得据旧分母声称完整。证据：references/full-runtime-registry.json；test-runs/MATH-FULL-record-20261105T145055Z-e554a714。
