# 使用指南

安装方式见[项目首页](../README.md)。发行包名为 `py-visactor-katex`，导入名为 `py_katex`。

## 渲染与导出

```python
from pathlib import Path
from py_katex import render

result = render(r"\int_0^1 x^2\,dx=\frac{1}{3}",
                display_mode=True, font_size=28,
                format="pdf", backend="cpu", background="white")
Path("formula.pdf").write_bytes(result.data)
```

`format` 支持 `png`、`jpg`、`jpeg`、`webp`、`svg`、`pdf`。`padding` 为外围逻辑留白；`density` 控制栅格导出密度。
`result.width`、`result.height` 是导出尺寸，`result.box` 包含数学盒及诊断。

`backend="auto"` 使用 Canvas 的默认设备策略；`cpu` 禁用 GPU；`gpu` 要求可用 GPU，不能创建时明确失败。
Canvas、字体和上下文归创建线程所有；跨线程传递纯数据和编码后的 `bytes`。

## 只排版或嵌入已有 Canvas

```python
from py_katex import Options, typeset

box = typeset(r"a^2+b^2=c^2", options=Options(font_size=24))
print(box.width, box.height, box.depth)
```

`box.height` 是基线上方高度，`box.depth` 是基线下方深度。`draw(context, box, x, y)` 使用公开 Canvas 2D 上下文，`(x, y)` 是公式左侧基线，y 轴向下；调用者负责画布尺寸和导出。

## 宏与请求隔离

```python
from py_katex import render

result = render(r"x\in\MyReals",
                macros={r"\MyReals": r"\mathbb{R}"}, backend="cpu")
```

默认每次解析独立，不修改调用方宏字典。显式共享状态时才使用 `MacroState`：

```python
from py_katex import MacroState, typeset

state = MacroState()
typeset(r"\def\MyReals{\mathbb{R}}", macro_state=state, global_group=True)
box = typeset(r"x\in\MyReals", macro_state=state)
```

宏值可为字符串、`Macro`、声明字典或显式 Python 回调。回调是调用方代码，不是 TeX 中执行的脚本。共享状态应按业务会话隔离。

## 编号与布局设置

`display_mode=True` 启用展示模式；`leqno` 将编号置左，`fleqn` 请求左对齐。
`content_width` 提供静态容器逻辑宽度，`equation_counter` 设置自动编号的初始计数。
手写编号可使用 `\tag{A}`。本模块不是完整 LaTeX 文档编译器。

## 显式离线资源

```python
from py_katex import ResourceBundle, image_resource_from_file, render

resources = ResourceBundle((image_resource_from_file("logo", "logo.png"),))
result = render(r"\includegraphics[width=2em]{logo}",
                resources=resources, trust=True, backend="cpu")
```

图片来自显式资源或 data URI；公式里的 URL 不自动触发文件或网络读取。
可用 `FontResource` 提供 Unicode 字体；缺字会明确诊断，系统字体回退不等于完整离线字库。
`html_styles` 可提供有限的静态类样式，不支持的可见属性会明确诊断，不是浏览器 CSS 宿主。

## 错误与预算

默认解析错误抛出 `ParseError`。`throw_on_error=False` 可以返回可见错误绘制，须检查 `result.box.diagnostics`。
`strict` 接受 `warn`、`ignore`、`error`、布尔值或显式回调；`trust` 接受布尔值或显式回调。
仅为可信内容启用相关静态命令。`max_expand`、`max_depth`、`max_nodes` 限制解析工作；关闭异常不等于绕过预算。

解析器的 `position` 使用 Python codepoint；错误另有 `utf16_position` 供 JS/宿主定位。两者遇到非 BMP 字符时可能不同。

## 命令行

```sh
python -m py_katex "x^2+y^2=z^2" --display --backend cpu -o formula.svg
py-katex --help
```

输出格式取自文件扩展名。支持 `--font-size`、`--macro NAME=EXPANSION`、`--strict`、`--no-throw`、`--image KEY=PATH`、`--font FAMILY=PATH`、`--html-style CLASS=DECLARATIONS` 等选项；完整参数以 `--help` 为准。
