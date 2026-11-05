"""Immutable parser, TeX box and native drawing contracts; no Canvas objects."""
from __future__ import annotations
from dataclasses import dataclass
from typing import Any
import math


class ParseError(ValueError):
    def __init__(self,message:str,position:int=0,code:str='PARSE_ERROR',length:int=1):
        super().__init__(message);self.position=position;self.code=code
        self.raw_message=message;self.rawMessage=message;self.length=length
        self.utf16_position=None


class MathWarning(UserWarning):
    """A fixed-source strict-mode diagnostic (never a swallowed exception)."""


@dataclass(frozen=True)
class Diagnostic:
    message:str
    position:int=0
    code:str='PARSE_ERROR'
    severity:str='error'


@dataclass(frozen=True)
class FontResource:
    family:str
    data:bytes
    scripts:tuple[str,...]=()
    style:str='normal'
    weight:str='normal'
    def __post_init__(self):
        if not isinstance(self.family,str) or not self.family.strip():raise ValueError('Font family must be nonempty')
        if not isinstance(self.data,bytes) or not self.data:raise ValueError('Font data must be immutable bytes')
        object.__setattr__(self,'scripts',tuple(self.scripts))


@dataclass(frozen=True)
class ImageResource:
    key:str
    data:bytes
    mime:str
    width:float
    height:float
    def __post_init__(self):
        if not isinstance(self.key,str) or not self.key:raise ValueError('Image resource key must be nonempty')
        if not isinstance(self.data,bytes) or not self.data:raise ValueError('Image resource must contain immutable bytes')
        for name in ('width','height'):
            value=getattr(self,name)
            if isinstance(value,bool) or not isinstance(value,(int,float)) or not math.isfinite(value) or value<=0:
                raise ValueError('Image resource dimensions must be finite and positive')


@dataclass(frozen=True)
class ResourceBundle:
    images:tuple[ImageResource,...]=()
    def __post_init__(self):
        images=tuple(self.images)
        if any(not isinstance(image,ImageResource) for image in images):raise TypeError('Expected ImageResource values')
        if len({image.key for image in images})!=len(images):raise ValueError('Duplicate image resource key')
        object.__setattr__(self,'images',images)
    def get(self,key):return next((image for image in self.images if image.key==key),None)


@dataclass(frozen=True)
class Node:
    kind:str
    value:str=''
    children:tuple[Node,...]=()
    attrs:tuple[tuple[str,Any],...]=()
    position:int=0
    def get(self,key,default=None):return dict(self.attrs).get(key,default)


@dataclass(frozen=True)
class Options:
    display_mode:bool=False
    font_size:float=20
    color:str='#000000'
    macros:tuple[tuple[str,Any],...]=()
    max_expand:int|float=1000
    max_depth:int=100
    max_nodes:int=20000
    trust:Any=False
    strict:Any='warn'
    throw_on_error:bool=True
    error_color:str='#cc0000'
    color_is_text_color:bool=False
    leqno:bool=False
    fleqn:bool=False
    max_size:float=math.inf
    min_rule_thickness:float=0
    global_group:bool=False
    macro_state:Any=None
    content_width:float|None=None
    equation_counter:int=0
    resources:ResourceBundle|None=None
    html_styles:tuple[tuple[str,str],...]=()
    fallback_fonts:tuple[FontResource,...]=()
    def __post_init__(self):
        if isinstance(self.font_size,bool) or not isinstance(self.font_size,(int,float)) or not math.isfinite(self.font_size) or not 0<self.font_size<=16384:
            raise ValueError('font_size must be finite and in (0, 16384]')
        if isinstance(self.max_expand,bool) or not isinstance(self.max_expand,(int,float)) or math.isnan(self.max_expand):
            raise ValueError('max_expand must be a number other than NaN')
        object.__setattr__(self,'max_expand',max(0,self.max_expand))
        for name,upper in [('max_depth',256),('max_nodes',1000000)]:
            value=getattr(self,name)
            if isinstance(value,bool) or not isinstance(value,int) or not 1<=value<=upper:raise ValueError(name+' exceeds its supported budget')
        entries=tuple(self.macros.items()) if hasattr(self.macros,'items') else tuple(self.macros)
        if any(not isinstance(key,str) for key,value in entries):raise TypeError('Macro names must be strings')
        object.__setattr__(self,'macros',entries)
        if not isinstance(self.color,str) or not self.color.strip():raise ValueError('color must be a nonempty CSS color')
        if not isinstance(self.error_color,str) or not self.error_color.strip():raise ValueError('error_color must be nonempty')
        if not (isinstance(self.strict,bool) or self.strict in ('warn','ignore','error') or callable(self.strict)):
            raise ValueError('strict must be a boolean, warn/ignore/error, or a callback')
        if not isinstance(self.trust,bool) and not callable(self.trust):raise TypeError('trust must be boolean or callback')
        for name in ('display_mode','throw_on_error','color_is_text_color','leqno','fleqn','global_group'):
            if not isinstance(getattr(self,name),bool):raise TypeError(name+' must be boolean')
        if isinstance(self.max_size,bool) or not isinstance(self.max_size,(int,float)) or math.isnan(self.max_size):
            raise ValueError('max_size must be a number other than NaN')
        object.__setattr__(self,'max_size',max(0,self.max_size))
        if isinstance(self.min_rule_thickness,bool) or not isinstance(self.min_rule_thickness,(int,float)) or not math.isfinite(self.min_rule_thickness):
            raise ValueError('min_rule_thickness must be finite')
        object.__setattr__(self,'min_rule_thickness',max(0,self.min_rule_thickness))
        if self.content_width is not None and (isinstance(self.content_width,bool) or not isinstance(self.content_width,(int,float)) or not math.isfinite(self.content_width) or self.content_width<=0):
            raise ValueError('content_width must be finite and positive')
        if isinstance(self.equation_counter,bool) or not isinstance(self.equation_counter,int) or self.equation_counter<0:
            raise ValueError('equation_counter must be nonnegative integer')
        if self.resources is not None and not isinstance(self.resources,ResourceBundle):raise TypeError('resources must be ResourceBundle')
        styles=tuple(self.html_styles.items()) if hasattr(self.html_styles,'items') else tuple(self.html_styles)
        if any(not isinstance(key,str) or not isinstance(value,str) for key,value in styles):raise TypeError('html_styles maps class names to declaration strings')
        object.__setattr__(self,'html_styles',styles)
        fonts=tuple(self.fallback_fonts)
        if any(not isinstance(font,FontResource) for font in fonts):raise TypeError('fallback_fonts requires FontResource values')
        object.__setattr__(self,'fallback_fonts',fonts)


@dataclass(frozen=True)
class Glyph:
    text:str
    x:float
    y:float  # baseline, positive downward; all coordinates logical pixels
    font:str  # bundled metric/font key e.g. Math-Italic, Main-Regular
    size:float
    color:str='#000000'
    scale_x:float=1.0
    font_resource:FontResource|None=None
    font_style:str|None=None
    font_weight:str|None=None


@dataclass(frozen=True)
class Rule:
    x:float
    y:float
    width:float
    height:float
    color:str='#000000'


@dataclass(frozen=True)
class Path:
    d:str
    x:float=0
    y:float=0
    scale_x:float=1
    scale_y:float=1
    color:str='#000000'
    stroke_width:float=0
    clip:tuple[float,float,float,float]|None=None  # local SVG units, after transform


@dataclass(frozen=True)
class ImageCommand:
    resource:ImageResource
    x:float
    y:float
    width:float
    height:float
    opacity:float=1


@dataclass(frozen=True)
class CommandGroup:
    commands:tuple[Command,...]
    x:float=0
    y:float=0
    scale_x:float=1
    scale_y:float=1
    opacity:float=1
    clip:tuple[float,float,float,float]|None=None
    matrix:tuple[float,float,float,float,float,float]=(1,0,0,1,0,0)
    filter:str='none'


Command=Glyph|Rule|Path|ImageCommand|CommandGroup


@dataclass(frozen=True)
class MathBox:
    width:float
    height:float  # ascent from baseline
    depth:float  # descent from baseline
    commands:tuple[Command,...]=()
    atom:str='mord'
    italic:float=0
    skew:float=0
    diagnostics:tuple[Diagnostic,...]=()
    @property
    def total_height(self):return self.height+self.depth


@dataclass(frozen=True)
class RenderResult:
    data:bytes
    width:int
    height:int
    mime:str
    box:MathBox
    backend:tuple[tuple[str,str],...]=()
