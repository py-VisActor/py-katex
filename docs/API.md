# Python API

公开入口来自 `py_katex`。完整示例见[使用指南](USER_GUIDE.md)。

| 入口 | 用途 |
| --- | --- |
| `parse(tex, *, macros=None, ...)` | 返回不可变 `Node` AST；解析预算、宏、展示模式和安全设置为关键字参数。 |
| `layout(tree, options=None)` | 将数学 AST 排为不可变 `MathBox`。 |
| `typeset(tex, *, options=None, font_size=None, display_mode=None, color=None, macros=None, **settings)` | 解析并排版，`settings` 对应 `Options` 字段。 |
| `render(tex, *, options=None, format='png', backend='auto', padding=8, background='transparent', density=1, quality=None, ...)` | 返回 `RenderResult`；排版选项可按关键字传入。 |
| `draw(context, box, x=0, y=0)` | 在调用方公开 Canvas 2D 上下文绘制；位置为左侧基线。 |
| `ink_bounds(box, context=None)` | 返回绘制内容的墨迹范围，区别于数学排版盒。 |

## 选项

`Options` 为冻结数据对象。主要字段如下；数值预算及资源会在入口校验。

| 类别 | 字段及默认值 |
| --- | --- |
| 外观 | `font_size=20`、`color='#000000'`、`display_mode=False` |
| 宏 | `macros=()`、`macro_state=None`、`global_group=False` |
| 预算 | `max_expand=1000`、`max_depth=100`、`max_nodes=20000` |
| 安全与错误 | `trust=False`、`strict='warn'`、`throw_on_error=True`、`error_color='#cc0000'` |
| 布局 | `leqno=False`、`fleqn=False`、`content_width=None`、`equation_counter=0` |
| 尺寸与样式 | `max_size=inf`、`min_rule_thickness=0`、`color_is_text_color=False` |
| 资源 | `resources=None`、`fallback_fonts=()`、`html_styles=()` |

`render()` 的默认导出后端为 `auto`，默认格式为 PNG。`Options` 不保存 Canvas 或上下文。

## 结果与诊断

- `MathBox`：`width`、基线上方 `height`、下方 `depth`、绘制 `commands`、`diagnostics`。
- `RenderResult`：编码 `data: bytes`、`width`、`height`、`mime`、`box`、实际 `backend` 信息。
- `ParseError`：`code`、`position`、`length`、`utf16_position`、`raw_message`/`rawMessage`；不应依赖完整英文消息文本。
- `Diagnostic` / `MathWarning`：静态诊断与严格模式警告。返回图片不表示没有诊断。

## 宏与资源对象

`MacroState` 显式保存跨调用宏状态；`Macro`、`Token` 支持高级宏扩展。
资源类型包括 `FontResource`、`ImageResource`、`ResourceBundle`；`image_resource()` 与 `image_resource_from_file()` 构造显式图片。
低层绘制命令类型包括 `Glyph`、`Rule`、`Path`、`ImageCommand`、`CommandGroup`。

生产入口不提供浏览器 DOM、HTML/MathML 输出或 JS 回调执行。
