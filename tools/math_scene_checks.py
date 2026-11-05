"""Independent pixel/geometry checks; a valid trace cannot stand in for ink."""
import io,math
from collections import Counter
from PIL import Image


def check(box,png,case,padding=10):
    image=Image.open(io.BytesIO(png)).convert('RGB');errors=[]
    commands=box['commands'];glyphs=[c for c in commands if c['type']=='Glyph'];rules=[c for c in commands if c['type']=='Rule'];paths=[c for c in commands if c['type']=='Path']
    numbers=[box[k] for k in ['width','height','depth']]
    if not all(math.isfinite(v) for v in numbers) or box['width']<0 or box['height']+box['depth']<0:errors.append('invalid TeX extents')
    ink=lambda pixel:min(pixel)<210
    if not any(ink(pixel) for pixel in image.getdata()):errors.append('blank native image')
    letters=Counter(''.join(g['text'] for g in glyphs))
    for character,count in Counter(case.get('glyphs','')).items():
        if letters[character]<count:errors.append('missing required glyph '+character)
    if len(rules)<case.get('minRules',0):errors.append('missing structural rule')
    if len(paths)<case.get('minPaths',0):errors.append('missing structural path')
    for font in case.get('fonts',[]):
        if not any(g['font']==font for g in glyphs):errors.append('missing requested math font '+font)
    # Sample actual native pixels on nonzero rules, independently of trace.
    baseline=padding+box['height']
    for rule in rules:
        if rule['width']<2 or rule['height']<=0:continue
        x0=max(0,math.floor(padding+rule['x']));x1=min(image.width,math.ceil(padding+rule['x']+rule['width']))
        y0=max(0,math.floor(baseline+rule['y']));y1=min(image.height,math.ceil(baseline+rule['y']+rule['height']))
        pixels=[image.getpixel((x,y)) for y in range(y0,y1) for x in range(x0,x1)]
        if pixels and not any(ink(pixel) for pixel in pixels):errors.append('missing actual rule pixels')
    # Mathematically stacked constructs must occupy multiple native baselines.
    if case.get('stacked') and len({round(g['y'],4) for g in glyphs})<2:errors.append('flattened mathematical baselines')
    return errors
