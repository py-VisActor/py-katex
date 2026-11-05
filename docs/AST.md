# Native math AST v1

Source: KaTeX 0.18.11 (`d5bed9f38a8d747b9c4a12e18897a514707e1c26`),
Lexer.ts, MacroExpander.ts, Namespace.ts, Parser.ts and functions/environments.
This is a pure-value layout contract; it does not recreate HTML/MathML nodes.
`Node(kind, value='', children=(), attrs=(), position=0)` is frozen.
`position` is the original Python codepoint offset; expansion tokens inherit
the macro invocation offset, while substituted arguments retain their locations.
The root is always `group`. No source or Canvas object is stored in the tree.

All command values below omit the leading backslash. Dimensions are immutable
`(number, unit)` pairs. Units are em/ex/mu/pt/mm/cm/in/bp/pc/dd/cc/nd/nc/sp/px.
Atoms are mord/mop/mbin/mrel/mopen/mclose/mpunct/minner.

| kind | value | children | attrs |
|---|---|---|---|
| group | empty | ordered body | none |
| symbol | actual Unicode glyph | none | atom, mode math/text, font source main/ams, original source token (preserves mathematical alphabet font identity) |
| atom | mathord/mathbin/mathrel/mathopen/mathclose/mathpunct/mathinner | body group | atom |
| scripts | empty | base, superscript group, subscript group | limits None/True/False; missing scripts are empty groups |
| frac | empty | numerator, denominator | bar bool, style auto/display/text/script/scriptscript, left/right delimiters, optional thickness dimension/None, align l/r/None, infix bool optional, continued bool for cfrac |
| sqrt | empty | radicand, index group | missing index is an empty group |
| operator | literal name or actual large-operator Unicode | optional body group | limits bool, symbol bool, command source identity, small bool for smallint, roman bool for operatorname versus mathop |
| delimiters | empty | successive body segment groups | left/right actual glyph or `.`, middle tuple, exactly one delimiter between adjacent children |
| sized_delimiter | actual delimiter | none | size 1/2/3/4, atom |
| font | source font command (mathrm/mathnormal/mathbf/mathit/mathbb/mathcal/mathscr/mathfrak/mathsf/mathsfit/mathtt/boldsymbol/bm) | body group | none |
| text | text/mbox/hbox/textnormal/textrm/textbf/textmd/textit/textup/textsf/texttt | body group | text mode preserved in contained symbols; embedded `$...$` is math |
| style | display/text/script/scriptscript | body group | cramped may be supplied by future source commands; layout derives normal fraction/script/root styles |
| size | tiny/sixptsize/scriptsize/footnotesize/small/normalsize/large/Large/LARGE/huge/Huge | body group | none |
| mathchoice | empty | display, text, script, scriptscript groups | layout selects using its current style |
| color | validated color string | body group | optional duplicated color attr |
| space | source command name | none | width in em |
| kern | empty | none | width dimension (negative permitted) |
| linebreak | empty | none | gap dimension/None; top-level source cr, separate from array row splitting |
| accent | source accent command | body group or symbol | normal/wide/stretchy source identity retained |
| line | overline/underline | body group | none |
| overunder | overbrace/underbrace/overset/underset/stackrel/stackbin | body, annotation group | over/underbrace annotation initially empty; outer scripts carry source annotation |
| xarrow | source extensible arrow command | above group, below group | missing below is empty group |
| phantom | phantom/hphantom/vphantom | body group | none |
| smash | empty | body group | smash_height, smash_depth bool |
| lap | llap/rlap/clap | body group | none |
| rule | empty | none | width, height, shift dimensions |
| raise | empty | body group | dy dimension |
| vcenter | empty | body group | layout centers total box on math axis |
| reflect | empty | body group | horizontal reflection; reflectbox is text mode and mathreflectbox is math mode |
| pmb | empty | body group | source static text-shadow offset 0.02em/0.01em with 0.04px blur |
| enclose | boxed/fbox/colorbox/fcolorbox/cancel/bcancel/xcancel/sout/phase/angl | body group | color=background and border_color=border optional |
| array | empty | row nodes | environment, cols tuple, left/right delimiter or empty, row_gaps tuple of dimension/None, hlines tuple of (row index,hline/hdashline), tag Node/None, arraystretch float/None |
| row | empty | cell group nodes | none |

For `array.cols`, l/c/r alignments and `|`/`:` rules retain order. A single
alignment repeats for matrix columns; aligned/align/gather/cases spacing is
chosen from environment identity by layout. Row gaps belong after each row.
`tag` is reserved for a measured annotation, not an interactive anchor; explicit tag macros remain unsupported in P1. `arraystretch` is an explicit current macro override, otherwise None lets layout use source environment defaults.

## Expansion, scope and safety

Lazy expansion uses a request-local macro namespace. Group braces, explicit
begingroup/endgroup and environments push scopes; def/newcommand/let are local,
gdef/xdef/global definitions replace all shadowing definitions within that request.
No macro survives a parse call. Replacement references use numbered parameters
1 through 9; def requires sequential parameter declarations, while newcommand
can consume more arguments (the fixed source explicitly tests ten). def also
records literal parameter delimiters. edef/xdef
expand the replacement before storing it. Source newcommand does not support
optional default arguments, and this parser does not invent them.

The packaged source-derived 315 literal macros are loaded as data. Context macros
are individually implemented or explicitly listed unsupported in the source map.
Unknown controls/environments fail with ParseError, never a literal-text formula.
Expansion count, queued token count, AST node count and recursive nesting have
explicit budgets. Trust does not enable URLs, HTML hosts, resource fetches or code.
href retains only its static label; url retains a literal typewriter label.
Terminal message/errmessage/show consume source arguments without host logging.
html@mathml selects the source visual branch as pure AST; it creates no HTML host.

## Compatibility boundaries

This contract is a substantive native math slice, not a claim of every KaTeX
command or option. Complete fixed-source command/environment inventories and
each unsupported branch are recorded in references/parser-sources.json.
The alpha P3 evidence is historical. The MATH-FULL additions below are P1 source
only until a new frozen candidate completes its own independent verification.

## MATH-FULL contract v2 (current)

Authority is the mechanically imported fixed-source runtime registry:
`references/full-runtime-registry.json`: 312 functions, 33 environments,
319 literal macros and 20 dynamic context macros. The former 334-name static
inventory omitted dynamic sizing names; it is not the current denominator.
All entries have native parser dispatch or a documented internal projection.
This statement is source completeness, not a behavioral compatibility score.

The parse keyword arguments now include `display_mode=False`, `strict='warn'`,
`color_is_text_color=False`, `global_group=False`, `error_color='#cc0000'`,
`macro_state=None`, `leqno=False`, and `throw_on_error=True`. `max_expand` accepts
numeric fractional thresholds and positive infinity; negative values clamp to
zero per the source Settings processor. Native node/depth/token budgets remain
independent. NaN and nonnumeric expansion thresholds are rejected.

`strict` supports bool, ignore/warn/error strings, or a Python callback receiving
(code, message, Token). Warnings use MathWarning. Source report=False branches
return strict behavior instead of throwing; callback failures there mean strict.
`trust` supports bool or a Python callback receiving the source command context
and validated protocol. Source strings are never executed as code.

| kind / extension | Native contract |
|---|---|
| tag | children=(body group, tag group); root remains group containing one tag; leqno bool |
| unsupported | value=original command, attrs color/rejected/code/message; visible source red command and warning diagnostic, never an empty successful formula |
| html | value=htmlClass/htmlId/htmlStyle/htmlData; children=(body group,); attributes tuple(name,value), for the native CSS provider |
| image | value=src; attrs src,alt,width,height,totalheight; dimensions are (number,unit), resource resolution is outside parser |
| cdarrow | value=> / < / A / V / = / pipe / dot; children=(first label,second label), reused inside array(environment=CD) |
| cdlabel | value=left/right; children=(label,); source internal vertical-arrow label layout |
| group | explicit=True for braces, semisimple=True for begingroup; reset_font/no_break for hbox; cd_parent=True for the internal CD wrapper |
| style | reset_font=True when source styling requests it |
| space | break_kind=allowbreak/nobreak, retained as static line-break opportunities |
| operator | always_handle_supsub and suppress_base_shift source flags; operatorname starred identity is separate from explicit limits |
| sqrt | index_provided distinguishes absent index from an explicitly empty optional index |
| xarrow | below_provided distinguishes absent and explicitly empty labels |
| text | verb=True requests source verb textstyle sizing rather than ordinary texttt sizing |
| delimiters | right_color preserves the scoped current color at right delimiter |

Arrays additionally expose `tags=None|tuple[Node|bool]`, `col_specs`, `add_jot`,
`hskip_before_after`, `col_separation`, `cell_style`, `leqno`. A col_spec is
('align', l/c/r, pregap dimension/None, postgap dimension/None), or
('separator', pipe/colon). True/False tag values are the source automatic-number
flags, not invented equation counters. Existing cols/row_gaps/hlines remain.
Each cell has its own macro scope; AMS row tags and nonumber use global TeX flags.
CD intentionally preserves the fixed source's terminal empty row.

Ordinary function arguments first consume raw balanced token arguments and then
parse an isolated expression. Primitive/script arguments parse one ordinary group
and enforce allowedInArgument. Optional arguments use unexpanded '[' lookahead.
Size extraction preserves the fixed source's unanchored measurement regex;
mandatory empty size groups mean 0pt, while empty optional sizes are invalid.
The fixed source cfrac has no [l]/[r] argument and is not extended to accept one.

MacroState is an explicit caller-owned mutable TeX namespace. Only that explicit
state object persists global definitions across parse calls. Ordinary macros
mappings remain unmodified. global_group=True also persists top-level definitions
to the state; otherwise a top-level TeX scope is closed while global defs survive.
Color and tag implementation flags are cleaned at the request boundary.

User macro values can be strings, Macro, source-style dictionaries, or Python
callbacks. Macro.body is in forward order; source dictionaries' tokens are in
reverse stack order, with numArgs/delimiters/unexpandable fields. Token preserves
native codepoint positions. Callback results are validated and budgeted and must
be a string, Macro, or expansion dictionary, not arbitrary code or another callback.

Callbacks receive Expander with the documented source aliases consumeArg,
consumeArgs, popToken, future, consumeSpaces, expandOnce, expandAfterFuture,
expandNextToken, expandTokens, expandMacro, expandMacroAsText, isDefined,
isExpandable, and a macros namespace facade. Source aliases retain reverse-stack
argument conventions; native argument/push/next methods use forward order.
The native namespace facade's current property is an inspection snapshot;
mutations go through its set method or the explicitly shared MacroState.

Unknown command handling under throw_on_error=False preserves the rest of the
formula and emits an unsupported node; true syntax failures still raise ParseError.
Native error.position stays codepoint-based; utf16_position is filled at parse exit
for comparison to the fixed JavaScript source. HTML/MathML serialization and
browser interactions are not native backends; their retained static content,
style, resources, semantics and security decisions are native responsibilities.
