"""Validated Python equivalent of KaTeX's public macro callback context."""
from dataclasses import dataclass
from collections.abc import Mapping
from .model import ParseError


@dataclass(frozen=True)
class MacroArgument:
    tokens: tuple
    start: object
    end: object


class NamespaceContext:
    def __init__(self,gullet):self.gullet=gullet
    def get(self,name):
        value=self.gullet.lookup(name)
        if value is not None and value.callback is not None:return value.callback
        return value.literal if value is not None and getattr(value,'literal',None) is not None else value
    def has(self,name):return self.gullet.lookup(name) is not None
    def set(self,name,value,global_=False):self.gullet.define(name,self.gullet.coerce(value) if value is not None else None,global_)
    def beginGroup(self):self.gullet.begin()
    def endGroup(self):self.gullet.end_group()
    @property
    def current(self):return dict(self.gullet.scopes[0])


def coerce_macro(g,value,position=0):
    from .macros import Macro,Token,lex
    if callable(value):return Macro((),callback=value)
    if isinstance(value,str):
        tokens=tuple(lex(value));count=0;stripped=value.replace('##','')
        while '#'+str(count+1) in stripped:
            count+=1
            if count>g.max_tokens:raise ParseError('Macro argument budget exceeded',position,'MAX_TOKENS')
        macro=Macro(tokens,count,literal=value)
    elif isinstance(value,Macro):macro=value
    elif isinstance(value,Mapping):
        raw=value.get('tokens')
        if not isinstance(raw,(list,tuple)):raise ParseError('Macro tokens must be an array',position,'INVALID_MACRO')
        tokens=[]
        for token in reversed(raw):
            if isinstance(token,Token):tokens.append(token)
            elif isinstance(token,str):tokens.append(Token(token,position))
            elif isinstance(token,Mapping) and isinstance(token.get('text'),str):tokens.append(Token(token['text'],position,noexpand=bool(token.get('noexpand',False)),treat_as_relax=bool(token.get('treatAsRelax',False))))
            else:raise ParseError('Invalid macro token',position,'INVALID_MACRO')
        delimiters=value.get('delimiters',())
        if not isinstance(delimiters,(tuple,list)) or any(not isinstance(d,(tuple,list)) or any(not isinstance(x,str) for x in d) for d in delimiters):raise ParseError('Invalid macro delimiters',position,'INVALID_MACRO')
        macro=Macro(tuple(tokens),value.get('numArgs',0),tuple(tuple(d) for d in delimiters),bool(value.get('unexpandable',False)))
    else:raise ParseError('Invalid macro definition or callback result',position,'INVALID_MACRO')
    if isinstance(macro.num_args,bool) or not isinstance(macro.num_args,int) or macro.num_args<0 or macro.num_args>g.max_tokens:raise ParseError('Invalid macro argument count',position,'INVALID_MACRO')
    if len(macro.body)>g.max_tokens or any(not isinstance(t,Token) or not isinstance(t.text,str) or isinstance(t.position,bool) or not isinstance(t.position,int) or t.position<0 for t in macro.body):raise ParseError('Macro token budget or type violation',position,'MAX_TOKENS')
    if macro.delimiters and len(macro.delimiters)!=macro.num_args+1:raise ParseError('Macro delimiter count mismatch',position,'INVALID_MACRO')
    return macro
