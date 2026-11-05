"""Render canonical retained cases on real native Canvas, preserving evidence."""
from __future__ import annotations
from pathlib import Path
import argparse,json,math,sys,traceback
from full_visual_support import (ROOT,ToolError,digest,normalized_case,pure,flatten_commands,decode_png,
    image_ink_bbox,required_characters,normalize_text,check_geometry,check_pixels,
    legacy_scene,native_origin,glyph_pixel_checks,image_decode_checks,path_pixel_checks)


def write(path,value):
    path.write_text(json.dumps(value,ensure_ascii=True,indent=2)+'\n',encoding='utf8')


def validate_one(case,oracle_dir,out,profile,root):
    row={'id':case.get('id','INVALID'),'status':'FAIL','errors':[],'checks':{},'kind':case.get('kind'),'sourceFixture':case.get('sourceFixture')}
    try:
        normalized=normalized_case(case,root=root);identity=normalized['id'];options=normalized['options']
        source_path=oracle_dir/(identity+'.json')
        if not source_path.is_file():raise ToolError('Official oracle metadata missing: '+str(source_path))
        official=json.loads(source_path.read_text(encoding='utf8'))
        if official.get('status') not in {'PASS','ERROR'}:raise ToolError('Unknown official oracle status')
        row['oracle']={'status':official['status'],'metadataSha256':digest(source_path.read_bytes()),'sourceTree':official.get('sourceTree'),'autoTagCount':official.get('autoTagCount',0),'expectedTagTexts':official.get('expectedTagTexts',[])}
        source_png=oracle_dir/(identity+'.png');oracle_image=None
        if official['status']=='PASS':
            if not source_png.is_file():raise ToolError('Official actual PNG missing')
            oracle_image=decode_png(source_png.read_bytes());row['oracle']['pngSha256']=digest(source_png.read_bytes());row['oracle']['inkBBox']=image_ink_bbox(oracle_image)
        from py_katex import typeset,ParseError
        from py_katex.canvas import render_box
        try:box=typeset(normalized['tex'],options=options)
        except Exception as error:
            row['nativeException']={'type':type(error).__name__,'message':str(error),'code':getattr(error,'code',None),'position':getattr(error,'position',None)}
            expected=case.get('expectedError') or case.get('kind') in {'negative','error','parse-error'}
            if official['status']=='ERROR' and expected:
                row['status']='PASS';row['classification']='EXPECTED_ERROR';row['checks']['expectedError']='PASS'
            else:row['errors'].append('Native typeset rejected retained case: '+str(error))
            write(out/(identity+'.metrics.json'),row);write(out/(identity+'.json'),row);return row
        padding=10
        result=render_box(box,format='png',backend=profile,padding=padding,background='white')
        image=decode_png(result.data)
        if image.size!=(result.width,result.height):row['errors'].append('Decoded PNG dimensions disagree with native result')
        renderer=dict(result.backend).get('renderer')
        if profile in {'cpu','gpu'} and renderer!=profile.upper():row['errors'].append('Requested backend selected another renderer')
        extent=native_origin(box);origin=(padding-extent[0],padding-extent[1]);flat=flatten_commands(box)
        row['checks']['imageDecodes']=image_decode_checks(box)
        scene=pure(box);scene['physical']={'width':result.width,'height':result.height,'origin':origin,'extent':extent};scene['flatCommands']=flat
        pngpath=out/(identity+'.png');pngpath.write_bytes(result.data);write(out/(identity+'.box.json'),scene)
        ink=image_ink_bbox(image);expected_ink=oracle_image is not None and image_ink_bbox(oracle_image) is not None
        row.update(width=result.width,height=result.height,logical={'width':box.width,'height':box.height,'depth':box.depth},origin=origin,inkBBox=ink,backend=dict(result.backend),pngSha256=digest(result.data),commandCounts={name:sum(item['type']==name for item in flat) for name in ('Glyph','Rule','Path','ImageCommand')},diagnostics=pure(box.diagnostics))
        if expected_ink and ink is None:row['errors'].append('Official image contains ink but native image is blank')
        # All encoded ink must fit the expanded physical viewport; this guard is
        # independent of logical TeX width (lap/smash/content-width can overflow).
        if ink is not None and (ink[0]<1 or ink[1]<1 or ink[2]>image.width-1 or ink[3]>image.height-1):row['errors'].append('Actual native ink touches physical viewport edge')
        dims=(box.width,box.height,box.depth)
        if not all(math.isfinite(value) for value in dims) or box.width<0 or box.height+box.depth<0:row['errors'].append('Invalid logical TeX extents')
        errors,detail=required_characters(case,official,flat);row['errors'].extend(errors);row['checks']['characters']=detail
        error_diagnostics=[item for item in box.diagnostics if item.severity=='error']
        if error_diagnostics:
            expected_codes=case.get('expectedDiagnostics')
            visible_rejection=options.trust is False and '\\' in str(official.get('visibleText','')) and all('TRUST' in item.code.upper() or 'REJECT' in item.code.upper() for item in error_diagnostics)
            if expected_codes is not None:
                missing=set(expected_codes)-{item.code for item in box.diagnostics}
                if missing:row['errors'].append('Missing expected diagnostics '+repr(sorted(missing)))
            elif not (not options.throw_on_error or visible_rejection):row['errors'].append('Unexpected error diagnostic in positive native output')
            row['diagnosticMode']='VISIBLE_REJECTION' if visible_rejection else 'NO_THROW' if not options.throw_on_error else 'DECLARED' if expected_codes is not None else 'UNEXPECTED'
        if official['status']=='ERROR':
            if case.get('sourceDefect'):row['classification']='DECLARED_SOURCE_DEFECT';row['sourceDefect']=case['sourceDefect']
            else:row['errors'].append('Official source rejected retained case without a declared source defect')
        # Verify actual glyph ROI ink, not just character/trace metadata.
        errors,detail=glyph_pixel_checks(image,flat,origin);row['errors'].extend(errors);row['checks']['glyphPixels']=detail
        errors,detail=path_pixel_checks(image,flat,origin);row['errors'].extend(errors);row['checks']['pathPixels']=detail
        errors,detail=check_geometry(box,flat,case.get('geometryChecks',[]));row['errors'].extend(errors);row['checks']['geometry']=detail
        pixel_specs=list(case.get('pixelChecks',[]))
        for probe in case.get('colorProbes',[]):pixel_specs.append({'type':'image_color','relativeX':probe['x'],'relativeY':probe['y'],'rgb':probe['rgb'],'tolerance':probe.get('tolerance',30)})
        errors,detail=check_pixels(image,flat,pixel_specs,origin);row['errors'].extend(errors);row['checks']['pixels']=detail
        # Preserve the existing source checker contract for old61 cases. Its
        # assumed origin is adapted in receipt coordinates, never in the PNG.
        from math_scene_checks import check as legacy_check
        legacy_case={key:case[key] for key in ('minRules','minPaths','fonts','stacked') if key in case}
        if legacy_case:
            errors=legacy_check(legacy_scene(box,flat,origin,padding),result.data,legacy_case,padding=padding)
            row['errors'].extend('legacy '+error for error in errors);row['checks']['legacy']=errors
        actual_text=normalize_text(''.join(item['text'] for item in flat if item['type']=='Glyph'))
        tagtexts=official.get('expectedTagTexts',[])
        if isinstance(tagtexts,str):tagtexts=[tagtexts]
        missing_tags=[value for value in tagtexts if normalize_text(value) not in actual_text]
        row['checks']['tags']={'autoTagCount':official.get('autoTagCount',0),'expectedTagTexts':tagtexts,'missing':missing_tags}
        if missing_tags:row['errors'].append('Missing visible source equation tags '+repr(missing_tags))
        row['status']='PASS' if not row['errors'] else 'FAIL'
        row['artifacts']={'png':identity+'.png','box':identity+'.box.json','metrics':identity+'.metrics.json'}
        write(out/(identity+'.metrics.json'),row);write(out/(identity+'.json'),row)
    except ToolError as error:
        row['status']='TOOL_ERROR';row['errors'].append(str(error));row['toolTraceback']=traceback.format_exc()
    except Exception as error:
        row['status']='FAIL';row['errors'].append(type(error).__name__+': '+str(error));row['traceback']=traceback.format_exc()
    if isinstance(row.get('id'),str) and __import__('re').fullmatch(r'[A-Za-z0-9][A-Za-z0-9_.-]{0,150}',row['id']):
        write(out/(row['id']+'.metrics.json'),row);write(out/(row['id']+'.json'),row)
    return row


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--fixtures',type=Path,required=True)
    parser.add_argument('--oracle',type=Path,required=True)
    parser.add_argument('--profile',choices=['cpu','auto','gpu'],required=True)
    parser.add_argument('--out',type=Path,required=True)
    args=parser.parse_args(argv)
    data=args.fixtures.read_bytes();fixtures=json.loads(data);cases=fixtures.get('cases')
    if not isinstance(cases,list):raise ToolError('Canonical fixtures require cases list')
    manifest_path=args.oracle/'manifest.json'
    if not manifest_path.is_file():raise ToolError('Official oracle manifest missing')
    manifest=json.loads(manifest_path.read_text(encoding='utf8'));input_sha=digest(data)
    if manifest.get('inputSha')!=input_sha:raise ToolError('Oracle manifest inputSha differs from canonical fixtures')
    ids=[case.get('id') for case in cases]
    if len(set(ids))!=len(ids):raise ToolError('Duplicate case IDs')
    args.out.mkdir(parents=True,exist_ok=False)
    rows=[validate_one(case,args.oracle,args.out,args.profile,ROOT) for case in cases]
    passed=all(row['status']=='PASS' for row in rows)
    report={'schema':'math-full-visual-report/v1','functionalStatus':'PASS' if passed else 'FAIL','profile':args.profile,'inputSha':input_sha,'fixtures':str(args.fixtures.resolve()),'oracleManifestSha256':digest(manifest_path.read_bytes()),'total':len(rows),'passed':sum(row['status']=='PASS' for row in rows),'failed':sum(row['status']=='FAIL' for row in rows),'toolErrors':sum(row['status']=='TOOL_ERROR' for row in rows),'cases':rows}
    write(args.out/'report.json',report)
    print(json.dumps({key:report[key] for key in ('schema','functionalStatus','profile','total','passed','failed','toolErrors')}))
    return 0 if passed else 1


if __name__=='__main__':raise SystemExit(main())
