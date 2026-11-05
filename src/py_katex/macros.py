"""Pure TeX tokens and scoped lazy expansion, ported from KaTeX 0.18.11.

Macro bodies are token values, never executable Python/JavaScript. Positions of
expanded tokens refer to the invocation in the original input.
"""
from __future__ import annotations
from collections import deque
from dataclasses import dataclass, replace
import re
from .model import ParseError


@dataclass(frozen=True)
class Token:
    text: str
    position: int = 0
    noexpand: bool = False
    treat_as_relax: bool = False
    source_comment: bool = False
    end: int | None = None


def lex(source: str, *, preserve_comments=False) -> list[Token]:
    result = []
    i = 0
    while i < len(source):
        start = i; c = source[i]
        if c == '%' and not preserve_comments:
            end = source.find('\n', i)
            i = len(source) if end < 0 else end + 1
            continue
        if c in ' \r\n\t':
            while i < len(source) and source[i] in ' \r\n\t': i += 1
            result.append(Token(' ', start,end=i)); continue
        if c == '\\':
            i += 1
            if i == len(source): raise ParseError('Bare backslash', start)
            word = re.match(r'[a-zA-Z@]+', source[i:])
            if word:
                name = word[0]; i += len(name)
                if name == 'verb' and i < len(source) and not source[i].isalpha():
                    if source[i] == '*': i += 1
                    if i == len(source): raise ParseError('Missing verb delimiter', start)
                    delimiter = source[i]; end = source.find(delimiter, i + 1)
                    if end < 0 or any(c in source[i+1:end] for c in '\n\r\u2028\u2029'): raise ParseError('Unterminated verb', start)
                    result.append(Token(source[start:end + 1], start)); i = end + 1; continue
                while i < len(source) and source[i] in ' \r\n\t': i += 1
                result.append(Token('\\' + name, start)); continue
            if source[i] in ' \r\n\t':
                while i < len(source) and source[i] in ' \r\n\t': i += 1
                result.append(Token('\\ ', start)); continue
            result.append(Token('\\' + source[i], start)); i += 1; continue
        if ord(c) < 32 or ord(c) in (0x2028,0x2029) or 0xD800 <= ord(c) <= 0xDFFF or 0xE000 <= ord(c) <= 0xF8FF:
            raise ParseError('Unexpected character', start, 'INVALID_CHARACTER')
        i += 1
        while i < len(source) and 0x300 <= ord(source[i]) <= 0x36F: i += 1
        result.append(Token(source[start:i], start,source_comment=c=='%' and preserve_comments,end=i))
    return result


@dataclass(frozen=True)
class Macro:
    body: tuple[Token, ...]
    num_args: int = 0
    delimiters: tuple[tuple[str, ...], ...] = ()
    unexpandable: bool = False
    handler: str = ''
    handler_data: tuple = ()
    callback: object = None
    literal: str | None = None
    @property
    def tokens(self):return tuple(reversed(self.body))
    @property
    def numArgs(self):return self.num_args
    def get(self,key,default=None):return {'tokens':self.tokens,'numArgs':self.num_args,'delimiters':self.delimiters,'unexpandable':self.unexpandable}.get(key,default)


class MacroState:
    """Explicit caller-owned TeX namespace; ordinary macro mappings stay immutable.

    Share only when persistent global definitions are wanted. Like a TeX job,
    one state object must not be mutated concurrently by independent callers.
    """
    def __init__(self, definitions=None):self.definitions=dict(definitions or {})
    def snapshot(self):return dict(self.definitions)
    def clear(self):self.definitions.clear()


class Expander:
    def __init__(self, text, macros=None, *, max_expand=1000, max_tokens=200000, builtins=None, symbol_groups=None, function_modes=None, state=None):
        self.tokens = deque(lex(text,preserve_comments=True)); self.end = len(text);self.source=text;self.raw_percent=False;self.strict_handler=None
        self.scopes = [dict()]; self.expansions = 0
        self.mode = 'math'
        self.symbol_groups = symbol_groups or {}
        self.function_modes = function_modes or {}
        self.max_expand = max_expand; self.max_tokens = max_tokens
        if len(self.tokens)>max_tokens:raise ParseError('Token budget exceeded',code='MAX_TOKENS')
        self.builtins={};self.state=state
        from .macro_context import NamespaceContext
        self.macros=NamespaceContext(self)
        if state is not None:
            if not isinstance(state,MacroState):raise ParseError('macro_state must be MacroState',code='INVALID_MACRO_STATE')
            self.scopes[0].update({k:self.coerce(v) for k,v in state.snapshot().items()})
        for name, body in {**(builtins or {}), **dict(macros or {})}.items():
            if not isinstance(name,str):raise ParseError('Macro names must be strings',code='INVALID_MACRO')
            (self.scopes[0] if name in dict(macros or {}) else self.builtins)[name] = self.coerce(body)
        for name in DYNAMIC_NAMES:
            self.builtins.setdefault(name,Macro((),callback=lambda context,name=name:context.dynamic_macro(name)))

    def dynamic_macro(self,name):
        token=getattr(self,'last_token',Token(name))
        self.dynamic(Token(name,token.position),counted=False)
        return Macro(())

    def coerce(self,value,position=0):
        from .macro_context import coerce_macro
        return coerce_macro(self,value,position)

    def begin(self): self.scopes.append({})
    def end_group(self):
        if len(self.scopes) < 2: raise ParseError('Extra endgroup')
        self.scopes.pop()
    def lookup(self, name):
        for scope in reversed(self.scopes):
            if name in scope:return scope[name] if scope[name] is not None else self.builtins.get(name)
        return self.builtins.get(name)
    def commit_state(self):
        if self.state is not None:
            self.state.definitions.clear();self.state.definitions.update({k:v for k,v in self.scopes[0].items() if v is not None})
    def define(self, name, macro, global_=False):
        if global_:
            for scope in self.scopes: scope.pop(name, None)
            self.scopes[0][name] = macro
        else: self.scopes[-1][name] = macro
    def raw(self):
        while self.tokens:
            token=self.tokens.popleft()
            if token.source_comment and not self.raw_percent:
                newline=self.source.find('\n',token.position)
                if newline<0:
                    self.tokens.clear()
                    if self.strict_handler:self.strict_handler('commentAtEnd','Comment has no terminating newline',token)
                else:
                    while self.tokens and self.tokens[0].position<=newline:
                        skipped=self.tokens.popleft()
                        if skipped.text==' ' and skipped.end is not None and skipped.end>newline+1:
                            self.tokens.appendleft(Token(' ',newline+1,end=skipped.end));break
                continue
            self.last_token=token
            return token
        return Token('EOF',self.end)
    def push(self, tokens):
        values = tuple(tokens)
        if len(self.tokens) + len(values) > self.max_tokens: raise ParseError('Token budget exceeded', code='MAX_TOKENS')
        self.tokens.extendleft(reversed(values))
        return len(values)
    def raw_nonspace(self):
        t = self.raw()
        while t.text == ' ': t = self.raw()
        return t
    def argument(self, delimiter=()):
        first = self.raw() if delimiter else self.raw_nonspace()
        self.last_argument_start=first.position
        if first.text == 'EOF': raise ParseError('Missing macro argument', first.position)
        if delimiter:
            result = []; depth = 0; match=0; self.push([first])
            while True:
                t = self.raw()
                if t.text == 'EOF': raise ParseError('Unterminated delimited macro argument', t.position)
                result.append(t)
                if t.text == '{': depth += 1
                if t.text == '}':
                    depth -= 1
                    if depth < 0: raise ParseError('Unexpected } in macro argument', t.position)
                if (depth==0 or (depth==1 and delimiter[match]=='{')) and t.text==delimiter[match]:
                    match+=1
                    if match==len(delimiter):result=result[:-match];break
                else:match=0
            if len(result)>=2 and first.text=='{' and result[-1].text=='}':result=result[1:-1]
            return result
        if first.text != '{':
            if first.text == '}': raise ParseError('Unexpected }', first.position)
            return [first]
        result = []; depth = 1
        while depth:
            t = self.raw()
            if t.text == 'EOF': raise ParseError('Unterminated macro argument', first.position)
            depth += (t.text == '{') - (t.text == '}')
            if depth: result.append(t)
        return result
    def expand_macro(self, token, macro, counted=True):
        if macro.callback is not None:
            macro=self.coerce(macro.callback(self),token.position)
            if macro.callback is not None:raise ParseError('Macro callback cannot return another callback',token.position,'INVALID_MACRO')
        self.expansions += int(counted)
        if self.expansions > self.max_expand: raise ParseError('Too many macro expansions', token.position, 'MAX_EXPAND')
        if macro.handler:
            one,old_single,old_double,middle,middle_double=macro.handler_data
            if one:
                self.define('|',old_single)
                if middle_double:self.define('\\|',old_double)
            doubled=macro.handler=='braket_double'
            if not doubled and middle_double and self.tokens and self.tokens[0].text=='|':self.raw();doubled=True
            return self.push(middle_double if doubled else middle)
        if macro.delimiters:
            for expected in macro.delimiters[0]:
                t = self.raw()
                if t.text != expected: raise ParseError('Macro prefix does not match', t.position)
        args = [self.argument(macro.delimiters[i+1] if macro.delimiters else ()) for i in range(macro.num_args)]
        body = []; i = 0
        while i < len(macro.body):
            t = macro.body[i]; i += 1
            if t.text == '#':
                if i == len(macro.body): raise ParseError('Incomplete macro parameter', token.position)
                p = macro.body[i]; i += 1
                if p.text == '#': body.append(Token('#', token.position)); continue
                if p.text not in '123456789' or int(p.text) > len(args): raise ParseError('Invalid macro parameter', token.position)
                body.extend(args[int(p.text)-1]); continue
            body.append(replace(t, position=token.position))
        return self.push(body)
    def is_expandable(self,name):
        macro=self.lookup(name)
        if macro is not None:return not macro.unexpandable
        if name in self.function_modes:return not self.function_modes[name][2]
        return name in DYNAMIC_NAMES
    def expand_tokens(self,tokens):
        saved=self.tokens;self.tokens=deque(tokens);output=[]
        try:
            while self.tokens:
                token=self.next(expandable_only=True)
                if token.text!='EOF':output.append(token)
        finally:self.tokens=saved
        self.expansions+=len(output)
        if self.expansions>self.max_expand:raise ParseError('Too many macro expansions',code='MAX_EXPAND')
        return output
    def next(self,expandable_only=False):
        while True:
            t = self.raw()
            if t.noexpand:
                if t.treat_as_relax and not expandable_only:return Token('\\relax',t.position)
                return replace(t,noexpand=False,treat_as_relax=False)
            macro = self.lookup(t.text)
            if macro is not None and expandable_only and macro.unexpandable:return t
            if macro is not None: self.expand_macro(t, macro); continue
            if self.dynamic(t) is not None: continue
            if expandable_only and t.text.startswith('\\') and not self.is_defined(t.text):raise ParseError('Undefined control sequence '+t.text,t.position,'UNKNOWN_COMMAND')
            return t

    # Source callback aliases retain source reverse-stack token conventions;
    # Python .argument/.push/.next remain explicit forward-order operations.
    def popToken(self):return self.raw()
    def pushToken(self,token):self.push([token])
    def pushTokens(self,tokens):self.push(reversed(tokens))
    def future(self):
        token=self.raw();self.push([token]);return token
    def consumeSpaces(self):
        token=self.raw_nonspace();self.push([token])
    def consumeArg(self,delims=None):
        from .macro_context import MacroArgument
        start=self.future();tokens=self.argument(tuple(delims or ()));end=getattr(self,'last_token',start)
        return MacroArgument(tuple(reversed(tokens)),start,end)
    def consumeArgs(self,count,delimiters=None):
        if delimiters:
            if len(delimiters)!=count+1:raise ParseError('Macro delimiter count mismatch')
            for value in delimiters[0]:
                if self.raw().text!=value:raise ParseError('Macro prefix mismatch')
        return [list(reversed(self.argument(tuple(delimiters[i+1]) if delimiters else ()))) for i in range(count)]
    def isDefined(self,name):return self.is_defined(name)
    def isExpandable(self,name):return self.is_expandable(name)
    def expandNextToken(self):return self.next()
    def expandTokens(self,tokens):return self.expand_tokens(tuple(reversed(tokens)))
    def expandMacro(self,name):return self.expand_tokens([Token(name)]) if self.lookup(name) is not None else None
    def expandMacroAsText(self,name):
        value=self.expandMacro(name);return None if value is None else ''.join(t.text for t in value)
    def expandOnce(self,expandableOnly=False):
        token=self.raw();macro=self.lookup(token.text)
        if macro is not None and not token.noexpand and not (expandableOnly and macro.unexpandable):
            return self.expand_macro(token,macro)
        dynamic=self.dynamic(token) if not token.noexpand else None
        if dynamic is not None:return dynamic
        if expandableOnly and token.text.startswith('\\') and not self.is_defined(token.text):raise ParseError('Undefined control sequence '+token.text,token.position)
        self.push([token]);return False
    def expandAfterFuture(self):self.expandOnce();return self.future()

    def dynamic(self, t, counted=True):
        """Source context macros which affect token expansion, not drawing."""
        command = t.text
        if command not in DYNAMIC_NAMES: return None
        output=0
        if counted:
            self.expansions += 1
            if self.expansions > self.max_expand: raise ParseError('Too many macro expansions', t.position, 'MAX_EXPAND')
        if command in ('\\newcommand','\\renewcommand','\\providecommand'):
            name=self.argument()
            if len(name)!=1:raise ParseError('newcommand first argument must be one macro name',t.position)
            name=name[0].text;exists=self.is_defined(name)
            if command=='\\newcommand' and exists:raise ParseError('Command already defined '+name,t.position)
            if command=='\\renewcommand' and not exists:raise ParseError('Command not defined '+name,t.position)
            body=self.argument();count=0
            if len(body)==1 and body[0].text=='[':
                pieces=[]
                while True:
                    token=self.next()
                    if token.text in (']','EOF'):break
                    pieces.append(token.text)
                number=''.join(pieces)
                if not re.fullmatch(r'\s*[0-9]+\s*',number):raise ParseError('Invalid macro argument count',t.position)
                if len(number.strip())>9:raise ParseError('Macro argument budget exceeded',t.position,'MAX_TOKENS')
                count=int(number)
                if count>self.max_tokens:raise ParseError('Macro argument budget exceeded',t.position,'MAX_TOKENS')
                body=self.argument()
            if command!='\\providecommand' or not exists:self.define(name,Macro(tuple(body),count))
        elif command=='\\tag@literal':
            if self.lookup('\\df@tag') is not None:raise ParseError('Multiple tag',t.position)
            output=self.expand_macro(t,Macro(tuple(lex(r'\gdef\df@tag{\text{#1}}')),1),counted=False)
        elif command in ('\\bra@ket','\\bra@set'):
            left,middle,middle_double,right=(tuple(self.argument()) for _ in range(4))
            data=(command=='\\bra@set',self.lookup('|'),self.lookup('\\|'),middle,middle_double)
            self.begin()
            try:
                self.define('|',Macro((),handler='braket_single',handler_data=data))
                if middle_double:self.define('\\|',Macro((),handler='braket_double',handler_data=data))
                body=self.argument();expanded=self.expand_tokens((*left,*body,*right))
            finally:self.end_group()
            output=self.push(expanded)
        elif command in ('\\message','\\errmessage','\\show'):
            # Source console diagnostics have no static visual output. Consume
            # their source arguments without invoking an external log/host.
            self.raw() if command=='\\show' else self.argument()
        elif command == '\\noexpand':
            tok = self.raw()
            if self.is_expandable(tok.text):tok=replace(tok,noexpand=True,treat_as_relax=True)
            output=self.push([tok])
        elif command == '\\expandafter':
            first = self.raw(); second = self.raw(); macro = self.lookup(second.text)
            if macro is not None:self.expand_macro(second, macro)
            elif self.dynamic(second) is None:self.push([second])
            output=self.push([first])
        elif command in ('\\@firstoftwo','\\@secondoftwo','\\TextOrMath'):
            first=self.argument();second=self.argument()
            output=self.push(first if command=='\\@firstoftwo' or (command=='\\TextOrMath' and self.mode=='text') else second)
        elif command == '\\@ifnextchar':
            test=self.argument();yes=self.argument();no=self.argument();next_=self.raw_nonspace();self.push([next_])
            output=self.push(yes if len(test)==1 and test[0].text==next_.text else no)
        elif command == '\\char':
            tok=self.raw();base=10
            if tok.text=='`':
                tok=self.raw()
                if tok.text=='EOF':raise ParseError('Missing char argument',t.position)
                number=ord(tok.text[1] if tok.text.startswith('\\') else tok.text[0])
            else:
                if tok.text in ("'",'"'):base=8 if tok.text=="'" else 16;tok=self.raw()
                digits='0123456789abcdef'[:base];number=0;count=0
                while len(tok.text)==1 and tok.text.lower() in digits:
                    number=number*base+int(tok.text,base);count+=1;tok=self.raw()
                self.push([tok])
                if not count:raise ParseError('Invalid char number',t.position)
            if number>0x10ffff or 0xd800<=number<=0xdfff:raise ParseError('Invalid Unicode codepoint',t.position)
            output=self.push([Token('\\@char',t.position),Token('{',t.position),*lex(str(number)),Token('}',t.position)])
        else:
            next_=self.raw();self.push([next_]);name=command
            if command=='\\dots':
                # Source expands the following token once before classifying it.
                following=self.expandAfterFuture();value=following.text
                if value in DOTS_BY_TOKEN:name=DOTS_BY_TOKEN[value]
                elif value.startswith('\\not') or self.symbol_groups.get(value) in ('bin','rel'):name='\\dotsb'
                else:name='\\dotso'
                return self.push(lex(name))
            endings={')',']','\\rbrack','\\}','\\rbrace','\\rangle','\\rceil','\\rfloor','\\rgroup','\\rmoustache','\\right','\\bigr','\\biggr','\\Bigr','\\Biggr','$',';', '.', ','}
            value='\\@cdots' if name=='\\cdots' else '\\ldots'
            if next_.text in endings and not (name=='\\dotsc' and next_.text==','):value+='\\,'
            output=self.push([replace(x,position=t.position) for x in lex(value)])
        return output

    def is_defined(self,name):
        return self.lookup(name) is not None or name in self.function_modes or name in self.symbol_groups or name in getattr(self,'defined_symbols',()) or name in DYNAMIC_NAMES or name in {'^','_','\\limits','\\nolimits'}


# Fixed macros.ts dotsByToken table, extracted as static Python values.
DOTS_BY_TOKEN = {',': '\\dotsc', '\\not': '\\dotsb', '+': '\\dotsb', '=': '\\dotsb', '<': '\\dotsb', '>': '\\dotsb', '-': '\\dotsb', '*': '\\dotsb', ':': '\\dotsb', '\\DOTSB': '\\dotsb', '\\coprod': '\\dotsb', '\\bigvee': '\\dotsb', '\\bigwedge': '\\dotsb', '\\biguplus': '\\dotsb', '\\bigcap': '\\dotsb', '\\bigcup': '\\dotsb', '\\prod': '\\dotsb', '\\sum': '\\dotsb', '\\bigotimes': '\\dotsb', '\\bigoplus': '\\dotsb', '\\bigodot': '\\dotsb', '\\bigsqcup': '\\dotsb', '\\And': '\\dotsb', '\\longrightarrow': '\\dotsb', '\\Longrightarrow': '\\dotsb', '\\longleftarrow': '\\dotsb', '\\Longleftarrow': '\\dotsb', '\\longleftrightarrow': '\\dotsb', '\\Longleftrightarrow': '\\dotsb', '\\mapsto': '\\dotsb', '\\longmapsto': '\\dotsb', '\\hookrightarrow': '\\dotsb', '\\doteq': '\\dotsb', '\\mathbin': '\\dotsb', '\\mathrel': '\\dotsb', '\\relbar': '\\dotsb', '\\Relbar': '\\dotsb', '\\xrightarrow': '\\dotsb', '\\xleftarrow': '\\dotsb', '\\DOTSI': '\\dotsi', '\\int': '\\dotsi', '\\oint': '\\dotsi', '\\iint': '\\dotsi', '\\iiint': '\\dotsi', '\\iiiint': '\\dotsi', '\\idotsint': '\\dotsi', '\\DOTSX': '\\dotsx'}

DYNAMIC_NAMES=frozenset(('\\noexpand','\\expandafter','\\@firstoftwo','\\@secondoftwo','\\@ifnextchar','\\TextOrMath','\\char','\\newcommand','\\renewcommand','\\providecommand','\\message','\\errmessage','\\show','\\dots','\\dotso','\\dotsc','\\cdots','\\tag@literal','\\bra@ket','\\bra@set'))
