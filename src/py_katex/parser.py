"""Python TeX parser, sourced from the pinned KaTeX parser/function families.

The AST is a pure native layout input, not KaTeX's DOM/MathML tree. See AST.md.
Unsupported control sequences always fail explicitly.
"""
from __future__ import annotations
from dataclasses import replace
from functools import lru_cache
import json
import math
from pathlib import Path
import re
import unicodedata
from .model import Node, ParseError
from .macros import Expander, Macro, Token, lex
from .unicode_scripts import SCRIPTS, SUBS
from .function_modes import FUNCTION_MODES, ARGUMENT_ALLOWED
from .parser_support import ParserSupport
from .parser_unicode import UNICODE_SYMBOLS, ACCENT_COMMANDS, SUPPORTED_RANGES

FONTS = frozenset('mathrm mathnormal mathbf mathit mathbb mathcal mathscr mathfrak mathsf mathsfit mathtt boldsymbol bm textnormal textrm textbf textmd textit textup textsf texttt Bbb bold frak'.split())
DECL_FONTS = {'rm':'mathrm','sf':'mathsf','tt':'mathtt','bf':'mathbf','it':'mathit','cal':'mathcal'}
ACCENTS = frozenset('acute grave ddot tilde bar breve check hat vec dot mathring widecheck widehat widetilde overrightarrow overleftarrow Overrightarrow overleftrightarrow overgroup overlinesegment overleftharpoon overrightharpoon underleftarrow underrightarrow underleftrightarrow undergroup underlinesegment utilde textcircled'.split())
TEXT_ACCENTS = {"'":'acute','`':'grave','^':'hat','~':'tilde','=':'bar','u':'breve','.':'dot','"':'ddot','c':'cedilla','r':'mathring','H':'hungarumlaut','v':'check'}
OPERATORS = frozenset('arcsin arccos arctan arctg arcctg arg ch cos cosec cosh cot cotg coth csc ctg cth deg dim exp hom ker lg ln log sec sin sinh sh tan tanh tg th det gcd inf lim max min Pr sup'.split())
LIMIT_OPS = frozenset('det gcd inf lim max min Pr sup'.split())
LARGE_OPS = dict(zip('sum prod coprod bigvee bigwedge biguplus bigcap bigcup intop bigotimes bigoplus bigodot bigsqcup smallint int iint iiint oint oiint oiiint'.split(), '∑ ∏ ∐ ⋁ ⋀ ⨄ ⋂ ⋃ ∫ ⨂ ⨁ ⨀ ⨆ ∫ ∫ ∬ ∭ ∮ ∯ ∰'.split()))
ENVIRONMENTS = frozenset('array darray matrix pmatrix bmatrix Bmatrix vmatrix Vmatrix matrix* pmatrix* bmatrix* Bmatrix* vmatrix* Vmatrix* smallmatrix subarray cases dcases rcases drcases align align* aligned split gather gather* gathered alignat alignat* alignedat equation equation*'.split())
SPACE = {',':1/6, ':':2/9, ';':5/18, '!':-1/6, 'quad':1, 'qquad':2,'enspace':.5,'enskip':.5,'thinspace':1/6,'medspace':2/9,'thickspace':5/18,'negthinspace':-1/6,'negmedspace':-2/9,'negthickspace':-5/18,' ':1/3,'space':1/3,'nobreakspace':1/3}
DELIMITERS = {'\\lbrace':'{','\\rbrace':'}','\\{':'{','\\}':'}','\\langle':'⟨','\\rangle':'⟩','\\lvert':'|','\\rvert':'|','\\vert':'|','\\lVert':'‖','\\rVert':'‖','\\Vert':'‖','\\|':'‖','\\lfloor':'⌊','\\rfloor':'⌋','\\lceil':'⌈','\\rceil':'⌉','\\backslash':'\\','\\uparrow':'↑','\\downarrow':'↓','\\updownarrow':'↕','\\Uparrow':'⇑','\\Downarrow':'⇓','\\Updownarrow':'⇕'}


def dimension_value(value, position=0, allow_blank=True):
    if value=='' and allow_blank:return 0.,'pt'
    match=re.search(r'([-+]?) *(\d+(?:\.\d*)?|\.\d+) *([a-z]{2})',value)
    units={'em','ex','mu','pt','mm','cm','in','bp','pc','dd','cc','nd','nc','sp','px'}
    if not match or match[3] not in units or not math.isfinite(float(match[1]+match[2])):raise ParseError('Invalid TeX dimension '+value,position,'INVALID_DIMENSION')
    return float(match[1]+match[2]),match[3]


@lru_cache(maxsize=1)
def _data():
    base = Path(__file__).with_name('data')
    symbols = json.loads((base/'symbols.json').read_text(encoding='utf-8'))
    macros_file = base/'macros.json'
    macros = json.loads(macros_file.read_text(encoding='utf-8')) if macros_file.is_file() else {}
    return symbols, macros


class Parser(ParserSupport):
    def __init__(self, tex, *, macros=None, max_expand=1000, max_depth=100, max_nodes=20000, trust=False, display_mode=False, strict='warn', color_is_text_color=False, global_group=False, error_color='#cc0000', macro_state=None, leqno=False, throw_on_error=True):
        if not isinstance(tex, str): raise ParseError('TeX must be a string', code='INVALID_INPUT')
        if isinstance(max_expand,bool) or not isinstance(max_expand,(int,float)) or math.isnan(max_expand):raise ParseError('Invalid max_expand',code='INVALID_LIMIT')
        max_expand=max(0,max_expand)
        for name, value in [('max_depth',max_depth),('max_nodes',max_nodes)]:
            if not isinstance(value,int) or isinstance(value,bool) or value < 0: raise ParseError('Invalid '+name, code='INVALID_LIMIT')
        self.symbols, builtins = _data()
        builtins={**builtins,'\\nonumber':r'\gdef\@eqnsw{0}','\\notag':r'\nonumber','\\operatorname':r'\@ifstar\operatornamewithlimits\operatorname@','\\hphantom':r'\smash{\phantom{#1}}'}
        self.g = Expander(tex, macros, builtins=builtins, max_expand=max_expand, max_tokens=max(1000,max_nodes*20),symbol_groups={k:v.get('group') for k,v in self.symbols.get('math',{}).items()},function_modes=FUNCTION_MODES,state=macro_state)
        self.cached = None; self.mode = 'math'; self.depth = 0; self.nodes = 0
        self.max_depth = max_depth; self.max_nodes = max_nodes; self.trust = trust
        self.display_mode=display_mode;self.strict=strict;self.color_is_text_color=color_is_text_color;self.global_group=global_group;self.error_color=error_color;self.leqno=leqno
        self.throw_on_error=throw_on_error
        self.g.strict_handler=self.handle_strict;self.expression_stops=[]
        self.g.defined_symbols=frozenset(self.symbols.get('math',{}))|frozenset(self.symbols.get('text',{}))
    def make(self, kind, value='', children=(), position=0, **attrs):
        self.nodes += 1
        if self.nodes > self.max_nodes: raise ParseError('Node budget exceeded',position,'MAX_NODES')
        return Node(kind,value,tuple(children),tuple(attrs.items()),position)
    def group(self, children=(), position=0): return self.make('group',children=children,position=position)
    def peek(self):
        self.g.mode = self.mode
        if self.cached is None: self.cached = self.g.next()
        return self.cached
    def take(self):
        t=self.peek();self.cached=None;return t
    def skip(self):
        while self.peek().text==' ':self.take()
    def expect(self,text):
        t=self.take()
        if t.text!=text:raise ParseError('Expected '+text+', got '+t.text,t.position)
        return t
    def flush(self):
        if self.cached is not None:self.g.push([self.cached]);self.cached=None
    def raw_argument(self):
        self.flush();return self.g.argument()
    def string_argument(self):
        return self.scan_string_tokens(self.raw_argument())
    def optional_string(self):
        tokens=self.optional_tokens()
        return None if tokens is None else self.scan_string_tokens(tokens)
    def argument(self,mode=None,primitive=False):
        old=self.mode
        if mode:self.mode=mode
        try:
            if not primitive:
                # A regex size parser can retain lookahead while scanArgument
                # reads the following raw argument. The source parser includes
                # that lookahead in the isolated argument expression, rather
                # than putting it back into the argument scanner.
                pending=self.cached;self.cached=None;tokens=self.g.argument()
                if pending is not None:tokens=[pending,*tokens]
                position=self.g.last_argument_start;end=getattr(self.g,'last_token',None)
                return self.subparse(tokens,self.mode,position,end.end or end.position+len(end.text) if end is not None else None)
            if self.mode=='math':self.skip()
            if self.peek().text=='{':return self.braced()
            while True:
                token=self.peek()
                if token.text in ('EOF','}','&','^','_','\\end','\\endgroup','\\right','\\over','\\atop','\\above','\\choose','\\brace','\\brack'):raise ParseError('Missing argument',token.position)
                if token.text in FUNCTION_MODES and not ARGUMENT_ALLOWED.get(token.text,False):raise ParseError('Function is not allowed without braces as an argument: '+token.text,token.position)
                result=self.atom(scripts=False)
                if result is not None:return self.group([result],result.position)
        finally:self.mode=old
    def braced(self):
        start=self.expect('{');self.depth+=1
        if self.depth>self.max_depth:raise ParseError('Depth budget exceeded',start.position,'MAX_DEPTH')
        self.g.begin()
        try:
            body=self.expression({'}'});self.expect('}');return self.make('group',children=body,position=start.position,explicit=True)
        finally:self.g.end_group();self.depth-=1
    def dimension(self):
        self.skip()
        position=self.peek().position
        if self.peek().text in ('EOF','}','&','\\end'):raise ParseError('Missing size argument',self.peek().position,'INVALID_DIMENSION')
        braced=self.peek().text=='{'
        if braced:value=self.string_argument()
        else:
            pieces=[]
            while self.peek().text in tuple('+-0123456789. '):pieces.append(self.take().text)
            self.skip()
            for _ in range(2):
                if self.peek().text in tuple('abcdefghijklmnopqrstuvwxyz'):pieces.append(self.take().text)
            self.peek()  # parseRegexGroup retains the first non-size lookahead.
            value=''.join(pieces)
        return dimension_value(value,position,allow_blank=braced)
    def expression(self,stops=frozenset(),break_infix=False):
        self.depth += 1
        if self.depth>self.max_depth:raise ParseError('Depth budget exceeded',self.peek().position,'MAX_DEPTH')
        self.expression_stops.append(stops)
        try:
            result=self._expression(stops,break_infix)
            return self.ligatures(result) if self.mode=='text' else result
        finally:self.depth-=1;self.expression_stops.pop()
    def _expression(self,stops=frozenset(),break_infix=False):
        body=[];infix=None
        while True:
            t=self.peek()
            if t.text=='EOF' or t.text in stops or t.text in ('}','\\endgroup','\\end','\\right','&'):break
            if self.mode=='math' and t.text==' ':self.take();continue
            if t.text in ('\\over','\\choose','\\atop','\\brace','\\brack','\\above'):
                if break_infix:break
                if infix is not None:raise ParseError('Only one infix fraction per group',t.position)
                self.take();thickness=self.dimension() if t.text=='\\above' else None
                numerator=self.group(body,t.position);denominator=self.group(self.expression(stops),t.position)
                if any(n.kind=='frac' and n.get('infix',False) for n in denominator.children):raise ParseError('Only one infix fraction per group',t.position)
                pair={'\\choose':('(',')'),'\\brace':('{','}'),'\\brack':('[',']')}.get(t.text,('',''))
                return [self.make('frac',children=(numerator,denominator),position=t.position,bar=t.text=='\\over' or (t.text=='\\above' and thickness[0]>0),left=pair[0],right=pair[1],style='auto',thickness=thickness,infix=True)]
            if t.text.startswith('\\') and t.text[1:] in ('color','displaystyle','textstyle','scriptstyle','scriptscriptstyle',*DECL_FONTS):
                self.take();cmd=t.text[1:]
                if cmd=='color':
                    value=self.color_argument();kind='color';self.g.define('\\current@color',Macro(tuple(lex(value))))
                elif cmd in DECL_FONTS:value=DECL_FONTS[cmd];kind='font'
                else:value=cmd[:-5];kind='style'
                body.append(self.make(kind,value,[self.group(self.expression(stops,break_infix=True),t.position)],t.position,reset_font=kind=='style'));continue
            node=self.atom()
            if node is not None:body.append(node)
        return body
    def atom(self,scripts=True):
        self.depth += 1
        if self.depth>self.max_depth:raise ParseError('Depth budget exceeded',self.peek().position,'MAX_DEPTH')
        try:return self._atom(scripts)
        finally:self.depth-=1
    def _atom(self,scripts=True):
        t=self.take();text=t.text
        if text in FUNCTION_MODES and not text.startswith('\\'):
            flags=FUNCTION_MODES[text]
            if (self.mode=='text' and not flags[0]) or (self.mode=='math' and not flags[1]):raise ParseError('Command is not allowed in '+self.mode+' mode',t.position)
        if text=='{':
            self.g.push([t]);base=self.braced()
        elif text in ('}','EOF','&','\\right','\\end','\\middle'):raise ParseError('Unexpected '+text,t.position)
        elif text in ('^','_') or (text=="'" and self.mode=='math'):
            if self.mode=='text':raise ParseError('Scripts are invalid in text mode',t.position)
            self.g.push([t]);base=self.group(position=t.position)
        elif text.startswith('\\verb') and len(text)>5:
            starred=text.startswith('\\verb*');offset=7 if starred else 6;content=text[offset:-1]
            if starred:content=content.replace(' ','␣')
            base=self.make('text','texttt',[self.group([self.make('symbol',c,position=t.position,atom='mord',mode='text',font='main',original=c) for c in content])],t.position,verb=True)
        elif text.startswith('\\'):base=self.command(t)
        elif text=='~':base=self.make('space','nobreakspace',position=t.position,width=1/3)
        elif text==' ' and self.mode=='text':base=self.make('space','space',position=t.position,width=1/3)
        elif self.mode=='math' and text in LARGE_OPS.values():
            base=self.make('operator',text,position=t.position,limits=text not in ('∫','∬','∭','∮','∯','∰'),symbol=True)
        elif text=='$' and self.mode=='text':
            base=self.math_switch('$',t.position)
        elif text in ('$','#'):raise ParseError('Unexpected '+text,t.position)
        else:base=self.symbol(text,t.position)
        if base is None or not scripts or self.mode!='math':return base
        sup=None;sub=None;limits=None
        while True:
            self.skip();next_=self.peek()
            if next_.text in ('\\limits','\\nolimits'):
                self.take()
                if base.kind!='operator':raise ParseError('Limit controls must follow an operator',next_.position)
                if base.get('command','').startswith('operatorname'):
                    if base.get('always_handle_supsub',False):limits=next_.text!='\\nolimits'
                else:limits=next_.text!='\\nolimits'
                base=replace(base,attrs=tuple({**dict(base.attrs),'always_handle_supsub':True}.items()));continue
            if next_.text=="'":
                self.take();primes=[self.symbol('\\prime',next_.position)]
                while self.peek().text=="'":primes.append(self.symbol('\\prime',self.take().position))
                if sup is not None:raise ParseError('Double superscript',next_.position)
                sup=self.group(primes,next_.position)
                if self.peek().text=='^':self.take();sup=self.group([sup,self.argument(primitive=True)],next_.position)
                continue
            if next_.text in SCRIPTS:
                is_sub=next_.text in SUBS;values=[]
                while self.peek().text in SCRIPTS and (self.peek().text in SUBS)==is_sub:
                    tok=self.take();values.append(SCRIPTS[tok.text])
                argument=self.subparse([Token(c,next_.position) for c in values], 'math', next_.position)
                if is_sub:
                    sub=argument
                else:
                    sup=argument
                continue
            if next_.text not in ('^','_'):break
            self.take();argument=self.argument(primitive=True)
            if next_.text=='^':
                if sup is not None:raise ParseError('Double superscript',next_.position)
                sup=argument
            else:
                if sub is not None:raise ParseError('Double subscript',next_.position)
                sub=argument
        if limits is not None and sup is None and sub is None:base=replace(base,attrs=tuple({**dict(base.attrs),'limits':limits}.items()))
        if sup is not None or sub is not None:return self.make('scripts',children=(base,sup or self.group(),sub or self.group()),position=t.position,limits=limits)
        return base
    def symbol(self,text,position):
        original=text
        if text and text[0] in UNICODE_SYMBOLS and text[0] not in self.symbols.get(self.mode,{}):
            if self.strict and self.mode=='math':self.handle_strict('unicodeTextInMathMode','Accented Unicode text in math mode',Token(text,position))
            text=UNICODE_SYMBOLS[text[0]]+text[1:]
        combining=re.search(r'[\u0300-\u036f]+$',text)
        if combining:
            marks=combining[0];base_text=text[:combining.start()]
            if base_text=='i':base_text='\u0131'
            elif base_text=='j':base_text='\u0237'
            base=self.symbol(base_text,position)
            for mark in marks:
                commands=ACCENT_COMMANDS.get(mark)
                if commands is None:raise ParseError('Unknown combining accent '+mark,position,'UNSUPPORTED_ACCENT')
                command=commands[0] if self.mode=='math' and commands[0] else TEXT_ACCENTS.get(commands[1],commands[1])
                base=self.make('accent',command,[base],position,stretchy=False,shifty=True,mode=self.mode)
            return base
        spec=self.symbols.get(self.mode,{}).get(text)
        if spec:
            if self.strict and self.mode=='math' and text in '\u00d0\u00de\u00fe':self.handle_strict('unicodeTextInMathMode','Latin text in math mode',Token(text,position))
            group=spec.get('group','mathord');atom={'mathord':'mord','textord':'mord','op-token':'mop','bin':'mbin','rel':'mrel','open':'mopen','close':'mclose','punct':'mpunct','inner':'minner','spacing':'mord'}.get(group,'mord')
            return self.make('symbol',spec.get('replace') or text,position=position,atom=atom,mode=self.mode,font=spec.get('font','main'),original=original)
        if text.startswith('\\'):
            if not self.throw_on_error:return self.make('unsupported',text,position=position,color=self.error_color,rejected=True,code='UNKNOWN_COMMAND',message='Undefined control sequence '+text)
            raise ParseError('Undefined control sequence: '+text,position,'UNKNOWN_COMMAND',length=len(text))
        if text.isalnum() or (len(text)==1 and ord(text)>127):
            if len(text)==1 and ord(text)>127:
                supported=any(start<=ord(text[0])<=end for start,end in SUPPORTED_RANGES)
                if self.strict and (not supported or self.mode=='math'):self.handle_strict('unicodeTextInMathMode' if supported else 'unknownSymbol','Unicode text character '+text,Token(text,position))
            return self.make('symbol',text,position=position,atom='mord',mode='text' if len(text)==1 and ord(text)>127 else self.mode,font='main',original=text)
        if text in '.,;:!?+-=*/()[]|<>':return self.make('symbol',text,position=position,atom={'+' : 'mbin','-':'mbin','*':'mbin','=':'mrel','<':'mrel','>':'mrel','(':'mopen',')':'mclose','[':'mopen',']':'mclose',',':'mpunct',';':'mpunct'}.get(text,'mord'),mode=self.mode,font='main')
        raise ParseError('Unsupported symbol '+text,position,'UNKNOWN_SYMBOL')
    def color_argument(self):
        value=self.string_argument()
        if not re.fullmatch(r'#[\da-fA-F]{3,4}|#[\da-fA-F]{6}|#[\da-fA-F]{8}|[\da-fA-F]{6}|[a-zA-Z]+',value):raise ParseError('Invalid color',getattr(self.g,'last_argument_start',0),'INVALID_COLOR')
        if re.fullmatch(r'[\da-fA-F]{6}',value):value='#'+value
        return value
    def delimiter(self,braced=False):
        self.skip()
        if braced and self.peek().text=='{':
            self.take();value=self.delimiter();self.expect('}');return value
        t=self.take();value=DELIMITERS.get(t.text,t.text)
        if t.text in ('{','}','\\'):raise ParseError('Invalid unescaped delimiter '+t.text,t.position)
        aliases={'\\lparen':'(','\\rparen':')','\\lbrack':'[','\\rbrack':']','<':'⟨','>':'⟩','\\lt':'⟨','\\gt':'⟩','\\lgroup':'⟮','\\rgroup':'⟯','\\lmoustache':'⎰','\\rmoustache':'⎱'}
        value=aliases.get(value,value)
        if value not in ('.','(',')','[',']','{','}','|','‖','⟨','⟩','⌊','⌋','⌈','⌉','/','\\','↑','↓','↕','⇑','⇓','⇕','⟮','⟯','⎰','⎱'):
            raise ParseError('Invalid delimiter '+t.text,t.position)
        return value
    def command(self,t):
        cmd=t.text[1:];pos=t.position
        if t.text not in FUNCTION_MODES and t.text not in self.symbols.get(self.mode,{}) and t.text!='\\begingroup':return self.symbol(t.text,pos)
        flags=FUNCTION_MODES.get(t.text)
        if flags and ((self.mode=='text' and not flags[0]) or (self.mode=='math' and not flags[1])):
            raise ParseError('Command '+t.text+' is not allowed in '+self.mode+' mode',pos)
        if cmd in ('\\globallong','\\globallet','\\globalfuture'):
            self.definition({'\\globallong':'long','\\globallet':'let','\\globalfuture':'futurelet'}[cmd],pos,True);return None
        if cmd in ('\\atopfrac','\\bracefrac','\\brackfrac','\\abovefrac'):
            numerator=self.argument();thickness=self.dimension() if cmd=='\\abovefrac' else None;denominator=self.argument()
            left,right={'\\bracefrac':('{','}'),'\\brackfrac':('[',']')}.get(cmd,('',''))
            return self.make('frac',children=(numerator,denominator),position=pos,bar=bool(thickness and thickness[0]>0),left=left,right=right,thickness=thickness,style='auto',continued=False)
        if cmd in ('\\cdleft','\\cdright'):return self.make('cdlabel',cmd[3:],[self.argument()],pos)
        if cmd=='\\cdparent':return self.make('group',children=(self.argument(),),position=pos,cd_parent=True)
        if cmd in ('\\cdrightarrow','\\cdleftarrow','\\cdlongequal'):
            below=self.optional_math();above=self.argument();return self.make('xarrow',cmd[1:],[above,below or self.group()],pos)
        if cmd in ('def','gdef','edef','xdef','newcommand','renewcommand','providecommand','let','futurelet','global','long'):
            self.definition(cmd,pos);return None
        if cmd in ('allowbreak','nobreak'):return self.make('space',cmd,position=pos,width=0.,break_kind=cmd)
        if cmd in ('relax','noindent','protect'):return None
        if cmd in ('hline','hdashline'):raise ParseError('Horizontal line is valid only inside an array',pos)
        if cmd=='verb':raise ParseError('verb ended without matching delimiter',pos)
        if cmd in (')',']'):raise ParseError('Mismatched math delimiter '+t.text,pos)
        if cmd=='(' and self.mode=='text':return self.math_switch('\\(',pos)
        if cmd=='\\':
            self.flush();gap=None
            if self.g.future().text=='[':
                self.g.raw();gap=self.scan_string_tokens(self.g.argument((']',)))
            if self.display_mode and self.handle_strict('newLineInDisplayMode','Newline does nothing in display mode',t,False):return self.make('space','',position=pos,width=0.)
            return self.make('linebreak',position=pos,gap=dimension_value(gap,pos,False) if gap is not None else None)
        if cmd in ('href','url'):return self.parse_href(cmd,pos)
        if cmd=='@char':
            number=self.string_argument()
            if not number.isdigit() or int(number)>0x10ffff:raise ParseError('Invalid character number',pos)
            return self.make('symbol',chr(int(number)),position=pos,atom='mord',mode=self.mode,font='main')
        if cmd=='html@mathml':
            # Source macro's visual branch; the alternate MathML tree is not an output backend.
            body=self.argument();self.argument();return body
        if cmd=='mathchoice':return self.make('mathchoice',children=[self.argument() for _ in range(4)],position=pos)
        if cmd=='begingroup':
            self.g.begin()
            try:body=self.expression({'\\endgroup'});self.expect('\\endgroup')
            finally:self.g.end_group()
            return self.make('group',children=body,position=pos,semisimple=True)
        if cmd in FONTS or cmd in ('text','mbox','hbox','vcenter','emph'):
            if cmd=='vcenter':return self.make('vcenter',children=[self.argument()],position=pos)
            mode='text' if cmd.startswith('text') or cmd in ('text','mbox','hbox') else 'math'
            if cmd=='emph':mode='text'
            body=self.argument(mode)
            if cmd=='hbox':return self.make('group',children=[body],position=pos,reset_font=True,no_break=True)
            return self.make('text' if mode=='text' else 'font',{'Bbb':'mathbb','bold':'mathbf','frak':'mathfrak','bm':'boldsymbol'}.get(cmd,cmd),[body],pos)
        if cmd in ('frac','dfrac','tfrac','cfrac','binom','dbinom','tbinom'):
            align=None
            a=self.argument('math');b=self.argument('math');binom='binom' in cmd
            return self.make('frac',children=(a,b),position=pos,bar=not binom,style='display' if cmd[0] in ('d','c') else 'text' if cmd[0]=='t' else 'auto',left='(' if binom else '',right=')' if binom else '',align=align,continued=cmd=='cfrac')
        if cmd=='genfrac':
            left_node=self.argument('math');right_node=self.argument('math')
            left=left_node.children[0].value if len(left_node.children)==1 and left_node.children[0].get('atom')=='mopen' else ''
            right=right_node.children[0].value if len(right_node.children)==1 and right_node.children[0].get('atom')=='mclose' else ''
            thickness=self.string_argument();style=self.string_argument();a=self.argument('math');b=self.argument('math')
            dim=None
            if thickness:
                dim=dimension_value(thickness,pos)
            if style not in ('','0','1','2','3'):raise ParseError('Invalid fraction style',pos)
            return self.make('frac',children=(a,b),position=pos,bar=dim is None or dim[0]>0,style={'':'auto','0':'display','1':'text','2':'script','3':'scriptscript'}[style],left=DELIMITERS.get(left,left),right=DELIMITERS.get(right,right),thickness=dim)
        if cmd=='sqrt':
            index=self.optional_math();body=self.argument('math',primitive=index is None);return self.make('sqrt',children=(body,index or self.group()),position=pos,index_provided=index is not None)
        if cmd in OPERATORS:return self.make('operator',cmd,position=pos,limits=cmd in LIMIT_OPS,symbol=False)
        if cmd in LARGE_OPS:return self.make('operator',LARGE_OPS[cmd],position=pos,limits=cmd not in ('int','iint','iiint','oint','oiint','oiiint'),symbol=True,small=cmd=='smallint',command=cmd)
        if cmd in ('operatorname','operatorname@','operatornamewithlimits','mathop'):
            star=False
            if cmd=='operatorname' and self.peek().text=='*':self.take();star=True
            body=self.argument('math',primitive=cmd=='mathop');return self.make('operator','',[body],pos,limits=False,symbol=False,roman=cmd!='mathop',command=cmd,always_handle_supsub=star or cmd=='operatornamewithlimits',suppress_base_shift=False)
        if cmd in ('mathord','mathbin','mathrel','mathopen','mathclose','mathpunct','mathinner'):
            return self.make('atom',cmd,[self.argument()],pos,atom={'mathord':'mord','mathbin':'mbin','mathrel':'mrel','mathopen':'mopen','mathclose':'mclose','mathpunct':'mpunct','mathinner':'minner'}[cmd])
        if cmd=='@binrel':
            prototype=self.argument();body=self.argument();node=prototype.children[0] if prototype.children else prototype
            atom=node.get('atom','mord');atom=atom if atom in ('mbin','mrel') else 'mord'
            return self.make('atom','math'+atom[1:],[body],pos,atom=atom)
        if cmd=='left':
            left=self.delimiter();segments=[];middle=[];self.g.begin()
            try:
                while True:
                    segments.append(self.group(self.expression({'\\middle','\\right'}),pos));end=self.take()
                    if end.text=='\\right':
                        right=self.delimiter();right_color=self.g.lookup('\\current@color')
                        right_color=''.join(x.text for x in self.g.expand_tokens([Token('\\current@color',pos)])) if right_color is not None else None
                        break
                    if end.text!='\\middle':raise ParseError('Missing right delimiter',pos)
                    middle.append(self.delimiter())
            finally:self.g.end_group()
            return self.make('delimiters',children=segments,position=pos,left=left,right=right,middle=tuple(middle),right_color=right_color)
        if re.fullmatch(r'(?:big|Big|bigg|Bigg)[lrm]?',cmd):
            delimiter=self.delimiter(braced=True);return self.make('sized_delimiter',delimiter,position=pos,size={'big':1,'Big':2,'bigg':3,'Bigg':4}[cmd.rstrip('lrm')],atom='mopen' if cmd.endswith('l') else 'mclose' if cmd.endswith('r') else 'mrel' if cmd.endswith('m') else 'mord')
        if cmd in ACCENTS or cmd in TEXT_ACCENTS:
            text_accent=cmd in TEXT_ACCENTS or cmd=='textcircled'
            if text_accent and self.mode=='math':self.handle_strict('mathVsTextAccents','Text accent in math mode',t)
            return self.make('accent',TEXT_ACCENTS.get(cmd,cmd),[self.argument(primitive=text_accent)],pos,mode='text' if text_accent else self.mode)
        if cmd in ('overline','underline'):return self.make('line',cmd,[self.argument()],pos)
        if cmd in ('overbrace','underbrace','overbracket','underbracket'):return self.make('overunder',cmd,[self.argument(),self.group()],pos)
        if cmd in ('overset','underset','stackrel','stackbin'):
            annotation=self.argument();body=self.argument();return self.make('overunder',cmd,[body,annotation],pos)
        if cmd.startswith('x') and cmd in ('xleftarrow','xrightarrow','xLeftarrow','xRightarrow','xleftrightarrow','xLeftrightarrow','xhookleftarrow','xhookrightarrow','xmapsto','xleftharpoonup','xleftharpoondown','xrightharpoonup','xrightharpoondown','xrightleftharpoons','xleftrightharpoons','xtofrom','xlongequal','xrightleftarrows','xtwoheadrightarrow','xtwoheadleftarrow','xrightequilibrium','xleftequilibrium'):
            below=self.optional_math();above=self.argument();return self.make('xarrow',cmd,[above,below or self.group()],pos,below_provided=below is not None)
        if cmd in SPACE:return self.make('space',cmd,position=pos,width=SPACE[cmd])
        if cmd in ('kern','mkern','hskip','mskip','hspace'):
            if self.peek().text=='*':self.take()
            return self.make('kern',position=pos,width=self.dimension())
        if cmd in ('phantom','hphantom','vphantom'):return self.make('phantom',cmd,[self.argument()],pos)
        if cmd=='smash':
            option=self.optional_math();height=option is None;depth=option is None
            if option is not None:
                for node in option.children:
                    if node.kind!='symbol':raise ParseError('Expected smash option symbol',node.position)
                    if node.value=='t':height=True
                    elif node.value=='b':depth=True
                    else:height=False;depth=False;break
            return self.make('smash',children=[self.argument()],position=pos,smash_height=height,smash_depth=depth)
        if cmd in ('llap','rlap','clap','mathllap','mathrlap','mathclap'):
            return self.make('lap',cmd.removeprefix('math'),[self.argument()],pos)
        if cmd in ('reflectbox','mathreflectbox','pmb'):
            return self.make('reflect' if 'reflectbox' in cmd else 'pmb',children=[self.hbox_argument() if cmd=='reflectbox' else self.argument()],position=pos)
        if cmd in ('rule','raisebox'):
            if cmd=='raisebox':dy=self.dimension();return self.make('raise',children=[self.hbox_argument()],position=pos,dy=dy)
            shift=self.optional_string();width=self.dimension();height=self.dimension();shift_dim=(0.,'em')
            if shift is not None:
                shift_dim=dimension_value(shift,pos,False)
            return self.make('rule',position=pos,width=width,height=height,shift=shift_dim)
        if cmd in ('textcolor','colorbox','fcolorbox'):
            color=self.color_argument();border=None
            if cmd=='fcolorbox':border=color;color=self.color_argument()
            body=self.hbox_argument() if cmd!='textcolor' else self.argument()
            return self.make('color' if cmd=='textcolor' else 'enclose',color if cmd=='textcolor' else cmd,[body],pos,color=color,border_color=border)
        if cmd in ('boxed','fbox','cancel','bcancel','xcancel','sout','phase','angl'):
            if cmd=='sout' and self.mode=='math':self.handle_strict('mathVsSout',"LaTeX's sout works only in text mode",t)
            return self.make('enclose',cmd,[self.hbox_argument() if cmd in ('fbox','angl') else self.argument()],pos)
        if cmd in ('tiny','sixptsize','scriptsize','footnotesize','small','normalsize','large','Large','LARGE','huge','Huge'):
            return self.make('size',cmd,[self.group(self.expression(self.expression_stops[-1] if self.expression_stops else set(),break_infix=True),pos)],pos)
        if cmd=='begin':return self.environment(self.string_argument(),pos)
        if cmd=='substack':
            self.skip();self.expect('{');self.g.begin();rows=[]
            try:
                while True:
                    rows.append(self.make('row',children=[self.group(self.expression({'\\\\','}'}),pos)],position=pos))
                    if self.take().text=='}':break
            finally:self.g.end_group()
            return self.make('array',children=rows,position=pos,environment='subarray',cols=('c',),left='',right='',row_gaps=(),hlines=())
        if cmd in ('htmlClass','htmlId','htmlStyle','htmlData'):return self.parse_html(cmd,pos)
        if cmd=='includegraphics':return self.parse_graphics(pos)
        return self.symbol(t.text,pos)
    def optional_math(self):
        tokens=self.optional_tokens()
        return None if tokens is None else self.subparse(tokens)
    def environment(self,name,pos):
        from .parser_arrays import environment
        return environment(self,name,pos)
    def definition(self,cmd,pos,global_=False):
        self.flush()
        if cmd in ('global','long'):
            t=self.g.next()
            while t.text==' ':t=self.g.next()
            if t.text not in ('\\global','\\def','\\gdef','\\edef','\\xdef','\\let','\\futurelet','\\long'):raise ParseError('Invalid macro prefix',pos)
            return self.definition(t.text[1:],pos,global_ or cmd=='global')
        name_tokens=self.g.argument() if cmd in ('newcommand','renewcommand','providecommand') else [self.g.raw_nonspace()]
        if len(name_tokens)!=1 or name_tokens[0].text in ('\\','{','}','$','&','#','^','_','EOF'):raise ParseError('Expected macro control sequence',pos,'INVALID_MACRO')
        name=name_tokens[0].text
        if cmd in ('let','futurelet'):
            tok=self.g.raw_nonspace()
            middle=None
            if cmd=='futurelet':middle=tok;tok=self.g.raw()
            elif tok.text=='=':
                tok=self.g.raw()
                if tok.text==' ':tok=self.g.raw()
            macro=self.g.lookup(tok.text) or Macro((replace(tok,noexpand=True),),unexpandable=not self.g.is_expandable(tok.text))
            self.g.define(name,macro,global_)
            if middle is not None:self.g.push([middle,tok])
            return
        if cmd in ('newcommand','renewcommand','providecommand'):
            exists=self.g.lookup(name) is not None or name in self.symbols.get('math',{}) or name[1:] in FONTS|OPERATORS|ACCENTS or name[1:] in ('frac','sqrt','begin')
            if cmd=='newcommand' and exists:raise ParseError('Command already defined '+name,pos,'INVALID_MACRO')
            if cmd=='renewcommand' and not exists:raise ParseError('Command is not defined '+name,pos,'INVALID_MACRO')
            count_text=self.optional_string()
            if count_text is not None:count_text=count_text.strip()
            count=int(count_text) if count_text and count_text.isdigit() else 0
            if count_text is not None and not count_text.isdigit():raise ParseError('Invalid macro argument count',pos)
            if count>self.max_nodes:raise ParseError('Macro argument budget exceeded',pos,'MAX_NODES')
            body=tuple(self.raw_argument())
            if cmd!='providecommand' or not exists:self.g.define(name,Macro(body,count),global_)
            return
        count=0;delimiters=[[]];insert=None
        while True:
            token=self.g.raw()
            if token.text=='{':self.g.push([token]);break
            if token.text=='EOF':raise ParseError('Missing macro definition',pos)
            if token.text=='#':
                index=self.g.raw()
                if index.text=='{':
                    insert=index;delimiters[count].append('{');self.g.push([index]);break
                if index.text!=str(count+1) or count>=9:raise ParseError('Macro parameters must be sequential',index.position)
                count+=1;delimiters.append([])
            else:delimiters[-1].append(token.text)
        body=tuple(self.g.argument())
        if insert is not None:body=(*body,insert)
        if cmd in ('edef','xdef'):
            body=tuple(self.g.expand_tokens(body))
        self.g.define(name,Macro(body,count,tuple(tuple(x) for x in delimiters)),global_ or cmd in ('gdef','xdef'))


def _parse_impl(tex: str, *, macros=None, max_expand=1000, max_depth=100, max_nodes=20000, trust=False, display_mode=False, strict='warn', color_is_text_color=False, global_group=False, error_color='#cc0000', macro_state=None, leqno=False, throw_on_error=True) -> Node:
    """Parse an isolated request into a pure immutable ``group`` root."""
    parser=Parser(tex,macros=macros,max_expand=max_expand,max_depth=max_depth,max_nodes=max_nodes,trust=trust,display_mode=display_mode,strict=strict,color_is_text_color=color_is_text_color,global_group=global_group,error_color=error_color,macro_state=macro_state,leqno=leqno,throw_on_error=throw_on_error)
    parser.g.define('\\df@tag',None,True)
    if not global_group:parser.g.begin()
    if color_is_text_color:parser.g.define('\\color',Macro(tuple(lex(r'\textcolor'))))
    try:
        body=parser.expression();parser.expect('EOF')
        while len(parser.g.scopes)>1:parser.g.end_group()
        tag=parser.take_tag()
        if tag is not None:
            if not display_mode:raise ParseError('tag works only in display equations')
            body=[parser.make('tag',children=[parser.group(body),tag],leqno=leqno)]
        return parser.group(body)
    except ParseError as exc:
        if getattr(exc,'utf16_position',None) is None:exc.utf16_position=len(tex[:exc.position].encode('utf-16-le','surrogatepass'))//2
        raise
    except RecursionError as exc:
        raise ParseError('Parser recursion budget exceeded',parser.peek().position,'MAX_DEPTH') from exc
    finally:
        while len(parser.g.scopes)>1:parser.g.end_group()
        for name in ('\\df@tag','\\current@color','\\color'):parser.g.scopes[0].pop(name,None)
        parser.g.commit_state()


def parse(tex: str, *, macros=None, max_expand=1000, max_depth=100, max_nodes=20000, trust=False, display_mode=False, strict='warn', color_is_text_color=False, global_group=False, error_color='#cc0000', macro_state=None, leqno=False, throw_on_error=True) -> Node:
    """Parse one native TeX job; construction and parser errors retain UTF16 provenance."""
    try:
        return _parse_impl(tex,macros=macros,max_expand=max_expand,max_depth=max_depth,max_nodes=max_nodes,trust=trust,display_mode=display_mode,strict=strict,color_is_text_color=color_is_text_color,global_group=global_group,error_color=error_color,macro_state=macro_state,leqno=leqno,throw_on_error=throw_on_error)
    except ParseError as exc:
        if isinstance(tex,str) and getattr(exc,'utf16_position',None) is None:exc.utf16_position=len(tex[:exc.position].encode('utf-16-le','surrogatepass'))//2
        raise
