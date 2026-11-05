"""Render TeX to a static file without a browser."""
from __future__ import annotations
import argparse,json,sys
from pathlib import Path
from . import render,ParseError,Options,ResourceBundle,FontResource


def main(argv=None):
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('expression')
    p.add_argument('-o','--output',type=Path,required=True)
    p.add_argument('--backend',choices=['cpu','auto','gpu'],default='auto')
    p.add_argument('--font-size',type=float,default=24)
    p.add_argument('--display',action='store_true')
    p.add_argument('--color',default='#000000')
    p.add_argument('--background',default='transparent')
    p.add_argument('--padding',type=float,default=8)
    p.add_argument('--density',type=int,default=1)
    p.add_argument('--macro',action='append',default=[],metavar='NAME=EXPANSION')
    p.add_argument('--strict',choices=['warn','ignore','error'],default='warn')
    p.add_argument('--trust',action='store_true',help='Enable static trusted commands; images still require explicit resources')
    p.add_argument('--no-throw',action='store_true',help='Render visible error text with diagnostics')
    p.add_argument('--error-color',default='#cc0000')
    p.add_argument('--leqno',action='store_true')
    p.add_argument('--fleqn',action='store_true')
    p.add_argument('--color-is-text-color',action='store_true')
    p.add_argument('--max-size',type=float,default=float('inf'))
    p.add_argument('--min-rule-thickness',type=float,default=0)
    p.add_argument('--max-expand',type=float,default=1000)
    p.add_argument('--content-width',type=float)
    p.add_argument('--equation-counter',type=int,default=0)
    p.add_argument('--image',action='append',default=[],metavar='KEY=PATH',help='Explicit offline image resource')
    p.add_argument('--font',action='append',default=[],metavar='FAMILY=PATH',help='Explicit offline Unicode fallback font')
    p.add_argument('--html-style',action='append',default=[],metavar='CLASS=DECLARATIONS')
    args=p.parse_args(argv);macros={}
    for item in args.macro:
        key,sep,value=item.partition('=')
        if not sep:p.error('--macro requires NAME=EXPANSION')
        macros[key]=value
    try:
        from .resources import image_resource_from_file,MAX_BYTES
        images=[];fonts=[];styles=[]
        for entries,kind in [(args.image,'image'),(args.font,'font'),(args.html_style,'html-style')]:
            for item in entries:
                key,sep,value=item.partition('=')
                if not sep or not key or not value:p.error('--'+kind+' requires a nonempty KEY=VALUE')
                if kind=='image':images.append(image_resource_from_file(key,value))
                elif kind=='font':
                    with Path(value).open('rb') as stream:data=stream.read(MAX_BYTES+1)
                    if len(data)>MAX_BYTES:raise ParseError('Font file byte budget exceeded',code='RESOURCE_BUDGET')
                    fonts.append(FontResource(key,data))
                else:styles.append((key,value))
        config=Options(strict=args.strict,trust=args.trust,throw_on_error=not args.no_throw,
            error_color=args.error_color,leqno=args.leqno,fleqn=args.fleqn,
            color_is_text_color=args.color_is_text_color,max_size=args.max_size,
            min_rule_thickness=args.min_rule_thickness,max_expand=args.max_expand,
            content_width=args.content_width,equation_counter=args.equation_counter,
            resources=ResourceBundle(tuple(images)),fallback_fonts=tuple(fonts),html_styles=tuple(styles))
        result=render(args.expression,options=config,font_size=args.font_size,display_mode=args.display,
            color=args.color,macros=macros,format=args.output.suffix.lstrip('.').lower(),
            backend=args.backend,padding=args.padding,background=args.background,density=args.density)
        args.output.parent.mkdir(parents=True,exist_ok=True);args.output.write_bytes(result.data)
        print(json.dumps({'output':str(args.output),'width':result.width,'height':result.height,
            'mime':result.mime,'backend':dict(result.backend),'diagnostics':[{'code':d.code,'message':d.message,'position':d.position,'severity':d.severity} for d in result.box.diagnostics]}))
        return 0
    except (ParseError,ValueError,TypeError,OSError) as error:
        print(json.dumps({'error':str(error),'code':getattr(error,'code','INVALID_ARGUMENT'),
            'position':getattr(error,'position',None)}),file=sys.stderr);return 1


if __name__=='__main__':raise SystemExit(main())
