> 2026-11-06 **固定 KaTeX 0.18.11 核心静态迁移已完成本地验收**：973 方法、684 上下文、1909 功能输入/217 等价关系、275 案例三后端与 297 历史流程图三后端通过。当前入口为 [完整验收](FULL_STATIC_ACCEPTANCE.md)。安装验证暂缓，未提交推送发布；下方旧 alpha/未实现状态仅作历史。

> 2026-11-05 MATH-FULL 扩展合同已落地，旧 v1 以下保留为基础。Options 增加 strict/trust 的 Python 回调、throw_on_error/error_color、color_is_text_color、leqno/fleqn、max_size/min_rule_thickness、global_group/macro_state、content_width(px)/equation_counter、resources/html_styles/fallback_fonts。max_expand允许非负数/Infinity（含小数阈值，负数按源钳0），节点/深度预算仍独立。parse详参以A新AST.md为准。
>
> FontResource(family,data,scripts,style,weight)，ImageResource(key,data,mime,width,height)，ResourceBundle(images).get(key)；Glyph末尾font_resource。新增ImageCommand(resource,x,y,width,height,opacity)和CommandGroup(commands,x,y,scale_x,scale_y,opacity,clip,matrix,filter)。矩阵是Canvas六元仿射，裁切为本地矩形，资源均纯不可变bytes。MathBox末尾diagnostics，visible noThrow/error不是成功公式；RenderResult通过box.diagnostics暴露。
>
> 20份数学字体仍使用固定源度量。只有原实现允许、且缺源数学度量的Unicode fallback支路才通过C的公开Canvas测量provider得到实际纯字形尺寸，返回box不包含native对象；支持显式FontResource离线优先和源宿主serif策略，实际字体受平台影响需单列。该支路修正旧“所有layout均完全无native测量”的过强表述，不复制字体shaping/Skia内部实现。

# MATH 接口 v1

纯值合同位于 src/py_katex/model.py。Node(kind,value,children,attrs,position) 的 attrs 为键值元组，get 查询。解析统一返回 kind=group 的根。parser.parse(tex, *, macros=None, max_expand=1000,max_depth=100,max_nodes=20000,trust=False) -> Node。

解析语义由 A 按来源定义并记录 docs/AST.md，B 读取后实现其各 kind；跨文件模型扩展由主协调处理。原子类别使用 mord/mop/mbin/mrel/mopen/mclose/mpunct/minner。未知控制序列、无效环境和预算超限抛 ParseError，position 为输入 Python codepoint offset，代码标明，后续兼容测试单列 UTF-16 对应。

B 提供 layout.layout(tree:Node, options:Options|None=None) -> MathBox。MathBox 的 width/height/depth 和 commands 都是逻辑像素，原点为基线左端，y 向下。height 是基线上方高度，depth 是基线下方深度，保留 TeX 合法负值，要求总 height+depth 非负。Glyph font 取 data/font_metrics.json 的字体键；x/y 为左端基线，size 为 px，scale_x 默认为 1，reflect 使用 -1。Rule 为填充矩形；Path 为纯路径值与缩放平移，stroke_width=0 时 fill，否则 stroke，末尾 clip 可提供 local SVG units 的裁剪矩形，在 transform 后使用。

C 提供 canvas.draw(context, box:MathBox, x=0,y=0)（x/y 是基线原点），以及 canvas.render_box(box, *, format='png',backend='auto',padding=8,background='transparent',density=1,quality=None)->RenderResult。Canvas、字体和 Image 都归调用线程；生产不得使用 Python 图片后处理代替原生绘制。20 个 KaTeX TTF 由 root 放入 data/fonts；C 显式注册稳定 family alias，source metric font key 不换成系统字体。

root 提供 typeset(tex, *, options=None, font_size=None, display_mode=None,color=None,macros=None) 及 render 公共包装；py-mermaid 通过 typeset/draw 接口消费纯 MathBox，禁止把表达式交给浏览器或 SVG 宿主重绘。公式应成为有 ascent/descent 的 inline 原子，支持普通文字与公式混排、换行和节点/边/组标签；Mermaid 的 $$ 分隔符按来源 displayMode=true。

scope：静态数学公式绘制与输入安全。HTML/MathML/浏览器宿主、超链接交互不作为输出后端；SVG/PDF 使用 Canvas 原生静态编码。不声称全部 KaTeX 命令兼容，命令/环境清单中保留实际未支持项。
