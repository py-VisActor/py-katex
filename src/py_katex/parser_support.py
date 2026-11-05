"""Fixed KaTeX settings, raw arguments and static HTML/image semantic handlers."""
from collections import deque
import re
import warnings
from .model import ParseError, MathWarning
from .macros import Token, Macro, lex


class ParserSupport:
    def handle_strict(self,code,message,token=None,report=True):
        behavior=self.strict
        if callable(behavior):
            if report:behavior=behavior(code,message,token)
            else:
                try:behavior=behavior(code,message,token)
                except Exception:behavior='error'
        if behavior is True or behavior=='error':
            if report:raise ParseError(message+' ['+code+']',getattr(token,'position',0),'STRICT_'+code)
            return True
        if behavior is False or behavior=='ignore':return False
        warnings.warn(message+' ['+code+']',MathWarning,stacklevel=3)
        return False

    def is_trusted(self,context):
        context=dict(context)
        if context.get('url') and not context.get('protocol'):
            match=re.search(r'^[\x00-\x20]*([^\\/#?]*?)(:|&#0*58|&#x0*3a|&colon)',context['url'],re.I)
            if not match:context['protocol']='_relative'
            elif match[2]!=':' or not re.fullmatch(r'[a-zA-Z][a-zA-Z0-9+.-]*',match[1]):return False
            else:context['protocol']=match[1].lower()
        return bool(self.trust(context) if callable(self.trust) else self.trust)

    def unsupported(self,command,position):
        return self.make('unsupported',command,position=position,color=self.error_color,rejected=True,code='UNTRUSTED_COMMAND',message='Untrusted command '+command)

    def subparse(self,tokens,mode=None,position=None,end=None):
        self.flush();saved=self.g.tokens;oldmode=self.mode
        tokens=tuple(tokens)
        boundary=end if end is not None else (tokens[-1].end or tokens[-1].position+len(tokens[-1].text)) if tokens else self.g.end
        self.g.tokens=deque((*tokens,Token('EOF',boundary)));self.cached=None
        if mode:self.mode=mode
        self.g.begin()
        try:
            body=self.expression();self.expect('EOF');return self.group(body,position if position is not None else tokens[0].position if tokens else 0)
        finally:
            self.g.end_group();self.g.tokens=saved;self.cached=None;self.mode=oldmode

    def take_tag(self):
        if self.g.lookup('\\df@tag') is None:return None
        tag=self.subparse([Token('\\df@tag')],'text')
        self.g.define('\\df@tag',None,True)
        return tag

    def raw_string(self):
        """Source raw argument expands tokens without constructing a math tree."""
        return self.string_argument()

    def scan_string_tokens(self,tokens):
        """parseStringGroup uses normal expansion, not expandTokens accounting."""
        self.flush();saved=self.g.tokens;self.g.mode=self.mode
        self.g.tokens=deque((*tokens,Token('EOF',self.g.end)));parts=[]
        try:
            while True:
                token=self.g.next()
                if token.text=='EOF':break
                parts.append(token.text)
        finally:self.g.tokens=saved
        return ''.join(parts)

    def optional_tokens(self):
        self.flush();self.g.consumeSpaces()
        if self.g.future().text!='[':return None
        self.g.raw();return self.g.argument((']',))

    def hbox_argument(self):
        return self.make('style','text',[self.argument('text')],reset_font=True)

    def url_argument(self):
        # KaTeX changes percent and tilde category codes while scanning URL data.
        # The lexer preserves comments in raw URL tokens via catcode-aware rescan.
        from dataclasses import replace
        self.flush();old=self.g.raw_percent;self.g.raw_percent=True
        try:tokens=self.g.argument()
        finally:self.g.raw_percent=old
        tokens=[replace(t,source_comment=False,noexpand=t.noexpand or t.text=='~') for t in tokens]
        value=self.scan_string_tokens(tokens)
        return re.sub(r'\\([#$%&~_^{}])',r'\1',value)

    def parse_graphics(self,pos):
        from .parser import dimension_value
        options=self.optional_string();width=(0.,'em');height=(.9,'em');totalheight=(0.,'em');alt=''
        if options is not None:
            for attribute in options.split(','):
                pair=attribute.split('=')
                if len(pair)!=2:continue
                key,value=pair[0].strip(),pair[1].strip()
                if key=='alt':alt=value;continue
                if key not in ('width','height','totalheight'):raise ParseError('Invalid includegraphics key '+key,pos)
                if re.fullmatch(r'[-+]? *(?:\d+(?:\.\d*)?|\.\d+)',value):measurement=(float(value.replace(' ','')),'bp')
                else:
                    match=re.search(r'([-+]?) *(\d+(?:\.\d*)?|\.\d+) *([a-z]{2})',value)
                    if not match:raise ParseError('Invalid includegraphics size '+value,pos)
                    measurement=dimension_value(match[1]+match[2]+match[3],pos)
                if key=='width':width=measurement
                elif key=='height':height=measurement
                else:totalheight=measurement
        source=self.url_argument()
        if not alt:
            name=re.split(r'[\\/]',source)[-1];alt=name[:name.rfind('.')] if '.' in name else ''
        if not self.is_trusted({'command':'\\includegraphics','url':source}):return self.unsupported('\\includegraphics',pos)
        return self.make('image',source,position=pos,src=source,alt=alt,width=width,height=height,totalheight=totalheight)

    def parse_html(self,command,pos):
        value=self.raw_string();body=self.argument();attributes={}
        if self.strict:self.handle_strict('htmlExtension','HTML extension is disabled in strict mode',Token('\\'+command,pos))
        field={'htmlClass':'class','htmlId':'id','htmlStyle':'style'}.get(command)
        if field:attributes[field]=value;context={'command':'\\'+command,field:value}
        else:
            items=[];current='';i=0
            while i<len(value):
                if value.startswith('{,}',i):current+=',';i+=3
                elif value[i]==',':items.append(current);current='';i+=1
                else:current+=value[i];i+=1
            items.append(current)
            for item in items:
                if '=' not in item:raise ParseError('htmlData key/value missing equals',pos)
                key,val=item.split('=',1);attributes['data-'+key.strip()]=val
            context={'command':'\\'+command,'attributes':dict(attributes)}
        if not self.is_trusted(context):return self.unsupported('\\'+command,pos)
        return self.make('html',command,[body],pos,attributes=tuple(attributes.items()))

    def parse_href(self,command,pos):
        target=self.url_argument()
        if command=='href':body=self.argument()
        else:
            # url.ts uses texttt and maps each raw character without TeX expansion.
            body=self.make('text','texttt',[self.group([self.make('symbol',c,position=pos,atom='mord',mode='text',font='main',original=c) for c in target])],pos)
        if not self.is_trusted({'command':'\\'+command,'url':target}):return self.unsupported('\\'+command,pos)
        # Static rendering retains content only, with no navigation host.
        return body

    def math_switch(self,opener,pos):
        old=self.mode;self.mode='math';closer='\\)' if opener=='\\(' else '$'
        try:body=self.expression({closer});self.expect(closer)
        finally:self.mode=old
        return self.make('style','text',[self.group(body,pos)],pos,reset_font=True)

    def ligatures(self,body):
        result=[];i=0
        while i<len(body):
            n=body[i];i+=1
            if n.kind=='symbol' and n.get('mode')=='text' and n.get('original',n.value) in ('-',"'",'`'):
                char=n.get('original',n.value);count=1
                while i<len(body) and count<(3 if char=='-' else 2) and body[i].kind=='symbol' and body[i].get('original',body[i].value)==char:
                    i+=1;count+=1
                if count>1:
                    text=char*count;spec=self.symbols.get('text',{}).get(text,{})
                    n=self.make('symbol',spec.get('replace',{'--':'–','---':'—',"''":'”','``':'“'}[text]),position=n.position,atom='mord',mode='text',font='main',original=text)
            result.append(n)
        return result
