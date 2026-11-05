"""Pure display-container/tag placement corresponding to KaTeX CSS.

KaTeX leaves its display container width to the embedding document. Native
callers can provide that width; an omitted width chooses a finite intrinsic
container large enough for body and tags, without an invisible host element.
"""
from dataclasses import replace
from .model import MathBox


def place_display(body, tags=(), *, em, content_width=None, leqno=False, fleqn=False):
    tags=tuple(tags)
    tag_width=max((box.width for box,y in tags),default=0.)
    indent=2*em if fleqn else 0.
    if content_width is None:
        width=body.width+indent+(2*(tag_width+em) if tags and not fleqn else tag_width+em if tags else 0.)
        body_x=indent if fleqn else (width-body.width)/2
        if fleqn and tags and leqno:body_x=max(body_x,tag_width+em)
        width=max(width,body_x+body.width)
    else:
        width=content_width;body_x=indent if fleqn else (width-body.width)/2
    commands=[replace(c,x=c.x+body_x) for c in body.commands]
    height=body.height;depth=body.depth;diagnostics=list(body.diagnostics)
    for box,y in tags:
        x=indent if leqno else width-box.width
        commands.extend(replace(c,x=c.x+x,y=c.y+y) for c in box.commands)
        height=max(height,box.height-y);depth=max(depth,box.depth+y)
        diagnostics.extend(box.diagnostics)
    return MathBox(width,height,depth,tuple(commands),body.atom,body.italic,body.skew,tuple(diagnostics))
