# Changelog

## 0.1.0 — 2026-11-06

First stable release of the native Python static mathematics renderer, based on
the pinned KaTeX 0.18.11 core.

- TeX parsing, scoped and persistent macros, display settings and diagnostics.
- Fractions, radicals, scripts, stretchy delimiters, accents and decorations.
- Arrays, AMS/CD environments, equation tags and numbering.
- Twenty bundled math fonts and original metrics; explicit offline resources.
- Static HTML style adaptation and accurate painted bounds.
- Native PNG, JPEG, WebP, SVG and PDF output using public py-skia-canvas APIs.
- `py-katex` command-line entry point and independent library APIs.

The core-static acceptance covers 973 test methods, 684 registration/macro
contexts, 1,909 upstream functional inputs, 217 equivalence pairs and 275
standalone/integration cases on CPU, auto and GPU in the recorded Windows
environment. Those records describe the original accepted development candidate;
release installation and artifact checks are recorded separately.

HTML/MathML serialization, arbitrary browser CSS, browser interactions and
independent contrib plugins (including mhchem) are outside this release's core
static scope. Non-math Unicode fonts can be supplied explicitly; platform fonts
are not a universal offline font collection.
