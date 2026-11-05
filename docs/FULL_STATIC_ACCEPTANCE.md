> 2026-11-06：正式发行任务另见 [发行状态](RELEASE_STATUS.md)。以下验收保持原始开发候选与 0.1.0a0 的历史口径，发行安装验证单独记录。

# KaTeX 核心静态迁移验收

2026-11-06：完成固定 KaTeX **0.18.11** 核心保留静态能力的本地迁移与 Mermaid 接入。版本仍为未发布的 `0.1.0a0`，版本号不表示本轮工作未验收。

## 本轮补齐

完整宏展开与作用域/持久状态、动态宏和回调、严格/信任/错误配置；AMS/CD、矩阵与数组、tag/自动编号、leqno/fleqn、尺寸限制与断行；字体轴、Unicode 回退、伸缩/重音/装饰、PMB；显式离线图片及 HTML 静态样式；真实墨迹边界、PNG/JPG/WebP/SVG/PDF 导出。Mermaid 节点、边、组标签通过独立 Python 模块绘制数学。

生产仅使用 Python 与公开 Canvas API，不依赖 Node、浏览器、JS 解释器或 DOM。20 个数学字体与源度量随包提供；其它 Unicode 字体可显式注入，系统回退不等于完整离线字库。

## 同候选验收

| 验证层 | 实际结果 |
| --- | --- |
| 新旧单元测试 | 973 个方法全部通过，无跳过 |
| 核心注册与宏 | 312 函数 + 33 环境 = 345 注册入口；339 宏；684 个合法/错误语义上下文 |
| 固定上游功能语料 | 1245 个来源测试条目中的 1909 个功能输入全部通过 |
| 正向等价关系 | 217 组全部通过 |
| 独立数学静态图 | 267 例 × CPU/auto/必需 GPU |
| Mermaid 数学集成 | 8 例 × 三后端；合计 825 份结果 |
| 历史流程图 | F01.1–F01.4 共 297 正例 × 三后端；负例、源错误与范围类别均保留 |
| 实际静态导出 | PNG、JPG、WebP、SVG、PDF 五种 |
| HTML 报告 | 825 视图、5 种下载、桌面/手机宽度通过；无外部请求 |

注册分母来自真实锁定源码注册，不是旧静态扫描的 334。孤立 `\]` 按源仅报错，其余内部入口通过真实消费上下文验证。功能语料检查接受/拒绝、诊断、决策回调及可见等价关系；**不声称执行或移植了原 Jest 全部私有树/HTML/MathML/snapshot 断言**。图像检查含实际像素、内容、字体轴、几何关系、资源和画布边界；跨 DOM/Canvas 像素不要求逐点一致。

## 可复核交付

[打开 HTML 对比报告](http://127.0.0.1:8765/MATH-FULL-batch-20261105T172308Z-e0e12af6/index.html)，包含固定官方 A 与 Python B 的原始 PNG、源输入、三后端筛选、原图及五格式下载。人工复核记录见机器摘要的 manual run；报告不会改写 A 图。

- 单元/语料：`test-runs/MATH-FULL-batch-20261105T171602Z-0d9b6942`
- 三后端/导出：`test-runs/MATH-FULL-batch-20261105T171857Z-5071cad7`
- 历史回归：`test-runs/MATH-FULL-batch-20261105T171629Z-8b5ef28e`
- 报告/浏览器 QA：`test-runs/MATH-FULL-batch-20261105T172308Z-e0e12af6`、`test-runs/MATH-FULL-batch-20261105T172348Z-4daa587b`
- 联合源码 SHA256：math `334c412c34ef675dbc223405622c8d4e19eb56b1ff3700c251cb663d4afdd445`；Mermaid `6094d419ff3c50d2c64fdd00051af2be087b25a7a239cb1dae0e9e09209fdff1`。

全部闭合 run 校验原始字节和源码未变；产品源码、验证输入、首轮全部失败与后续修复均保留。曾经自动全通过但人工发现字体轴、SVG 比例和样式框问题的候选被明确拒收，记录见 [人工拒收候选](../references/full-manual-rejected-candidate.json)。最初失败输入已按原日志 SHA256 重建，保存在新的恢复 run，未修改旧 run。最终文档审计入口为 `test-runs/MATH-FULL-batch-20261105T172451Z-dcedc8c2`。机器摘要见 [full-verification-summary.json](../references/full-verification-summary.json)，复用步骤见 [FULL_RUNS_AND_REPORTS.md](FULL_RUNS_AND_REPORTS.md)。

## 明确范围与差异

核心静态目标已验收；HTML/MathML 输出后端、任意浏览器宿主 CSS 引擎、交互/无障碍 DOM 行为，以及独立 contrib 插件分别分类，未计作原生通过。`mhchem` 是独立扩展，未移植；auto-render/copy-tex/mathtex-script 的浏览器集成不在静态目标。静态样式通过有限的原生属性适配，不支持的可见属性明确诊断。

固定 Mermaid 的元数据反斜线损坏、MathML 组标题字体和边界空格差异在报告逐例说明；不把对损坏源的修正写成与异常画面等价。相同源的 fleqn/leqno 标号重叠也保留来源说明。字体栅格、留白和自然尺寸差异允许，遗漏内容与错误关系不得通过。

安装/构建验证按用户要求暂缓；本机 Windows 证据不能证明 Linux/no-loader 环境。源码与报告均未提交、推送或发布。历史 alpha 验收仍保留，但不能证明当前候选。
