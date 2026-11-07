"""Exercise an installed distribution with -I; no source checkout imports."""
from pathlib import Path
import argparse
import hashlib
import importlib.metadata
import importlib.resources
import json
import shutil
import sys


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--out', type=Path, required=True)
    p.add_argument('--expected-version', required=True)
    p.add_argument('--backend', choices=['cpu', 'auto', 'gpu'], default='cpu')
    args = p.parse_args()
    import py_katex
    from py_katex import render, typeset, MacroState, ParseError, ResourceBundle, image_resource
    from py_skia_canvas import Canvas, Image
    assert sys.flags.isolated, 'Run the installed smoke with python -I'
    assert py_katex.__version__ == importlib.metadata.version('py-visactor-katex') == args.expected_version
    assert Path(py_katex.__file__).resolve().is_relative_to(Path(sys.prefix).resolve())
    assert importlib.metadata.version('py-skia-canvas') == '0.1.0a18'
    args.out.mkdir(parents=True, exist_ok=False)
    fonts = list(importlib.resources.files('py_katex').joinpath('data/fonts').iterdir())
    assert len([f for f in fonts if f.name.endswith('.ttf')]) == 20
    samples = []

    def sample(name, tex, **options):
        result = render(tex, backend=args.backend, background='white', **options)
        assert not result.box.diagnostics, (name, result.box.diagnostics)
        data = result.data
        (args.out / name).write_bytes(data)
        ink = None
        if name.endswith('.png'):
            image = Image(data)
            assert (image.width, image.height) == (result.width, result.height)
            canvas = Canvas(image.width, image.height)
            canvas.gpu = False
            ctx = canvas.getContext('2d')
            ctx.drawImage(image, 0, 0)
            pixels = bytes(ctx.getImageData(0, 0, image.width, image.height).data)
            ink = sum(pixels[i + 3] > 0 and min(pixels[i:i + 3]) < 235 for i in range(0, len(pixels), 4))
            assert ink > 4, (name, 'No real painted pixels')
        samples.append({'file': name, 'sha256': hashlib.sha256(data).hexdigest(),
                        'bytes': len(data), 'width': result.width, 'height': result.height,
                        'backend': dict(result.backend), 'paintedPixels': ink})

    formula = r'x=\frac{-b\pm\sqrt{b^2-4ac}}{2a}'
    for fmt, header in [('png', b'\x89PNG'), ('jpg', b'\xff\xd8'), ('webp', b'RIFF'), ('svg', b'<'), ('pdf', b'%PDF')]:
        sample('formula.' + fmt, formula, font_size=32, display_mode=True, format=fmt)
        assert (args.out / ('formula.' + fmt)).read_bytes().lstrip().startswith(header)
    for name, tex, options in [
        ('matrix', r'\begin{pmatrix}a&b\\c&d\end{pmatrix}', {}),
        ('cd', r'\begin{CD} A @>f>> B \\ @VgVV @VVhV \\ C @>>k> D \end{CD}', {'display_mode': True}),
        ('tag', r'x+y\tag{A}', {'display_mode': True, 'leqno': True, 'content_width': 400}),
        ('font-axes', r'\htmlStyle{font-family:KaTeX_SansSerif;font-style:italic;font-weight:bold}{1}', {'trust': True}),
        ('html-frame', r'\htmlStyle{background-color:yellow;border:2px solid blue;padding:6px;color:red}{x}', {'trust': True, 'font_size': 40}),
        ('stretch', r'\left\{\frac{a}{b}\right\}\xrightarrow{x+y}\widehat{abc}', {}),
    ]:
        sample(name + '.png', tex, **options)
    svg = b'<svg xmlns="http://www.w3.org/2000/svg" width="40" height="20" viewBox="0 0 40 20"><path fill="red" d="M0 0H20V20H0Z"/><path fill="blue" d="M20 0H40V20H20Z"/></svg>'
    sample('resource.png', r'\includegraphics[width=2em,totalheight=1.4em]{quad}',
           resources=ResourceBundle((image_resource('quad', svg, mime='image/svg+xml'),)), trust=True)
    state = MacroState()
    typeset(r'\def\ReleaseReals{\mathbb{R}}', macro_state=state, global_group=True)
    sample('macro.png', r'x\in\ReleaseReals', macro_state=state)
    try:
        typeset(r'\frac{1}')
    except ParseError:
        pass
    else:
        raise AssertionError('Malformed TeX was silently accepted')
    visible_error = render(r'\frac{1}', backend=args.backend, throw_on_error=False)
    assert visible_error.box.diagnostics
    assert not any(name in sys.modules for name in ['py_mermaid', 'pyelk', 'skia'])
    receipt = {'status': 'PASS', 'project': 'py-visactor-katex', 'version': py_katex.__version__, 'installedModule': py_katex.__file__,
               'isolated': True, 'python': sys.version, 'backend': args.backend,
               'nodeAvailable': bool(shutil.which('node')), 'bundledFonts': 20, 'samples': samples}
    (args.out / 'smoke.json').write_text(json.dumps(receipt, indent=2) + '\n', 'utf-8')
    print(json.dumps({'status': 'PASS', 'samples': len(samples), 'backend': args.backend, 'module': py_katex.__file__}))


if __name__ == '__main__':
    main()
