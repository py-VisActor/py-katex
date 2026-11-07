"""Python mathematics parsing, layout and static native Canvas rendering."""
from __future__ import annotations
from dataclasses import replace
from .model import (Node,Options,MathBox,Glyph,Rule,Path,ParseError,RenderResult,
                    MathWarning,Diagnostic,FontResource,ImageResource,ResourceBundle,ImageCommand,CommandGroup)
from .parser import parse
from .layout import layout

__version__='0.1.1'


def typeset(tex,*,options=None,font_size=None,display_mode=None,color=None,macros=None,**settings):
    config=options or Options()
    changes={key:value for key,value in [('font_size',font_size),('display_mode',display_mode),('color',color)] if value is not None}
    if macros is not None:changes['macros']=tuple(macros.items()) if hasattr(macros,'items') else tuple(macros)
    config=replace(config,**changes,**settings)
    try:
        tree=parse(tex,macros=dict(config.macros),max_expand=config.max_expand,max_depth=config.max_depth,
                   max_nodes=config.max_nodes,trust=config.trust,display_mode=config.display_mode,
                   strict=config.strict,color_is_text_color=config.color_is_text_color,
                   global_group=config.global_group,error_color=config.error_color,macro_state=config.macro_state,
                   throw_on_error=config.throw_on_error,leqno=config.leqno)
        return layout(tree,config)
    except ParseError as error:
        if config.throw_on_error:raise
        # Source noThrow is a visible error rendering, distinguishable from a
        # successfully typeset formula through the box's diagnostic values.
        text=str(tex)
        if len(text)>config.max_nodes:
            # A diagnostic must not bypass the caller's independent node budget.
            text=text[:max(1,config.max_nodes-1)]+'…'
        tree=Node('error',text,attrs=(('message',str(error)),('code',error.code)),position=error.position)
        return layout(tree,replace(config,color=config.error_color))


def draw(context,box,x=0,y=0):
    from .canvas import draw as implementation
    return implementation(context,box,x,y)


def render(tex,*,options=None,font_size=None,display_mode=None,color=None,macros=None,
           format='png',backend='auto',padding=8,background='transparent',density=1,quality=None,**settings):
    from .canvas import render_box
    box=typeset(tex,options=options,font_size=font_size,display_mode=display_mode,color=color,macros=macros,**settings)
    return render_box(box,format=format,backend=backend,padding=padding,background=background,density=density,quality=quality)


def __getattr__(name):
    if name in ('MacroState','Macro','Token'):
        from . import macros
        return getattr(macros,name)
    if name in ('image_resource','image_resource_from_file'):
        from . import resources
        return getattr(resources,name)
    if name=='ink_bounds':
        from .canvas import ink_bounds
        return ink_bounds
    raise AttributeError(name)


__all__=['parse','layout','typeset','draw','render','Node','Options','MathBox','Glyph','Rule','Path',
         'ParseError','RenderResult','MathWarning','Diagnostic','FontResource','ImageResource','ResourceBundle',
         'ImageCommand','CommandGroup','MacroState','Macro','Token','image_resource','image_resource_from_file','ink_bounds']
