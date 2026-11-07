# py-katex

Python TeX 数学公式解析、排版与静态绘制，基于 KaTeX 0.18.11 核心移植。
数学字体和度量随包提供；通过公开 `py-skia-canvas` API 输出 PNG、JPEG、WebP、SVG、PDF，运行时无需 Node、浏览器或联网字体。

## 安装

```sh
python -m pip install py-visactor-katex==0.1.1
```

发行名为 `py-visactor-katex`，导入名为 `py_katex`，命令行为 `py-katex`。
需要 CPython 3.13；当前原生依赖支持 Windows AMD64 和 Linux glibc 2.28+ x86_64。

## 最小示例

```python
from pathlib import Path
from py_katex import render

result = render(r"x=\frac{-b\pm\sqrt{b^2-4ac}}{2a}",
                font_size=28, display_mode=True, backend="cpu", format="svg")
Path("formula.svg").write_bytes(result.data)
```

```sh
py-katex "x^2+y^2=z^2" --display --backend cpu -o formula.png
```

## 能力与边界

支持符号、字体、分式、根式、脚标、极限、伸缩括号与重音、矩阵、AMS/CD 环境、编号、作用域宏与显式离线资源。
默认错误会抛出异常；选择可见错误输出时应检查诊断，不能将错误图当作成功公式。
HTML/MathML 序列化、任意浏览器 CSS、交互和独立 contrib 插件（如 mhchem）不属于核心静态范围；不承诺与浏览器逐像素相同。

## 文档

- [用户文档](https://github.com/py-VisActor/py-katex/blob/main/docs/README.md)：使用指南、API、宏与资源。
- [更新记录](https://github.com/py-VisActor/py-katex/blob/main/CHANGELOG.md) · [问题反馈](https://github.com/py-VisActor/py-katex/issues)
- [维护者与 AI agent 入口](https://github.com/py-VisActor/py-katex/blob/main/docs/development/README.md)

MIT License；KaTeX 与字体归属见[第三方声明](https://github.com/py-VisActor/py-katex/blob/main/THIRD_PARTY_NOTICES.md)。
