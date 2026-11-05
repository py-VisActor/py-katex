# py-katex

Python TeX 数学公式解析、二维排版与静态绘制，基于固定 **KaTeX 0.18.11** 核心移植。
数学字体和原始度量随包提供，通过 `py-skia-canvas` 公开 API 输出 PNG、JPEG、WebP、SVG 和 PDF。
生产运行不需要 Node、浏览器、JavaScript 引擎或联网字体。

## 安装

```shell
python -m pip install py-katex==0.1.0
```

需要 CPython **3.13**。原生依赖固定为 `py-skia-canvas==0.1.0a18`，其发行 wheel 支持
Windows AMD64 和 Linux glibc 2.28+ x86_64。其他 ABI、架构和 macOS 不在当前发行依赖范围内。
默认 `auto` 保留 Canvas 设备策略；`cpu` 禁用 GPU，`gpu` 要求实际 GPU，不能创建时明确失败。

## Python API

```python
from pathlib import Path
from py_katex import Options, render, typeset

formula = r"x=\frac{-b\pm\sqrt{b^2-4ac}}{2a}"
result = render(formula, font_size=28, display_mode=True,
                backend="cpu", format="svg", background="white")
Path("formula.svg").write_bytes(result.data)
box = typeset(formula, options=Options(font_size=28, display_mode=True))
print(box.width, box.height, box.depth)
```

`parse` 返回数学 AST，`layout`/`typeset` 返回不可变数学盒，`render` 返回编码字节、尺寸、
实际后端和数学盒。`draw(context, box, x, y)` 可绘制到调用方的 Canvas；原点是左侧基线，y 向下。
Canvas、Context 和字体对象属于调用线程，跨线程只传纯数据和 bytes。

```python
from py_katex import MacroState, render, typeset

state = MacroState()
typeset(r"\def\MyReals{\mathbb{R}}", macro_state=state, global_group=True)
result = render(r"x\in\MyReals\tag{A}", macro_state=state,
                display_mode=True, leqno=True, content_width=400, backend="cpu")
```

默认请求隔离，不修改调用方宏字典。宏支持字符串、`Macro`、声明字典和显式 Python 回调；
`strict`/`trust` 可使用显式 Python 回调，不执行源字符串。`content_width` 是静态容器逻辑宽度，
`equation_counter` 指定自动编号起点。

## 离线资源

```python
from py_katex import ResourceBundle, image_resource_from_file, render

resources = ResourceBundle((image_resource_from_file("logo", "logo.png"),))
result = render(r"\includegraphics[width=2em]{logo}",
                resources=resources, trust=True, backend="cpu")
```

图片仅来自显式资源或 data URI，公式 URL 不会自动访问网络或文件。
可通过 `FontResource` 注入 Unicode 字体；系统回退不等于完整离线字库，缺字会明确报错。
`html_styles` 将类名映射为有限的静态样式声明；不支持的可见属性明确诊断。

## 命令行

```shell
py-katex "x^2+y^2=z^2" --display --backend cpu -o formula.png
python -m py_katex "x^2+y^2=z^2" --display --backend cpu -o formula.pdf
```

输出格式由扩展名决定。另有 `--macro`、`--strict`、`--no-throw`、`--image KEY=PATH`、
`--font FAMILY=PATH`、`--html-style CLASS=DECLARATIONS` 等选项。

## 范围和错误

核心静态能力包括符号与字体、分式/根式、脚标/极限、积分/求和、伸缩括号/箭头/重音、
矩阵与 AMS/CD、tag/编号、作用域宏、尺寸/断行、颜色/装饰、可信任静态图片与样式。
20 个数学 TTF 与固定源度量随包提供。Python 原生位置使用 codepoint，解析错误另附 UTF-16 对应位置。

`throw_on_error=False` 绘制可见错误提示；必须检查 `result.box.diagnostics`，不能将错误图当作成功公式。
默认遇到错误抛出 `ParseError`。独立资源预算与解析预算限制异常输入。

HTML/MathML 输出、任意浏览器宿主 CSS、交互和独立 contrib 插件（如 mhchem）不属于核心静态范围。
字体栅格、留白和自然尺寸不作跨 DOM/Canvas 逐像素等价承诺。
py-mermaid 的数学标签可使用此模块；宿主预处理和混排规则由 py-mermaid 负责。

## 来源与验收

来源固定 KaTeX 0.18.11 / `d5bed9f38a8d747b9c4a12e18897a514707e1c26`。
开发候选验收覆盖 973 个测试方法、684 个注册/宏上下文、1,909 个来源功能输入、217 组等价关系与
275 个数学/集成案例三后端。发行安装验证单独记录；历史报告保留其实际候选与版本。

- [完整静态验收](https://github.com/py-VisActor/py-katex/blob/main/docs/FULL_STATIC_ACCEPTANCE.md)
- [发行状态](https://github.com/py-VisActor/py-katex/blob/main/docs/RELEASE_STATUS.md)
- [更新记录](https://github.com/py-VisActor/py-katex/blob/main/CHANGELOG.md)
- [日志与报告复用](https://github.com/py-VisActor/py-katex/blob/main/docs/FULL_RUNS_AND_REPORTS.md)
- [第三方声明](https://github.com/py-VisActor/py-katex/blob/main/THIRD_PARTY_NOTICES.md)

MIT License。保留 KaTeX 的 MIT 许可证和来源声明。
