/* Development-only TS source loader. No install, build, mutation, or formulas. */
import fs from 'node:fs';
import path from 'node:path';
import {fileURLToPath,pathToFileURL} from 'node:url';
import {registerHooks,stripTypeScriptTypes} from 'node:module';

export const root=path.resolve(path.dirname(fileURLToPath(import.meta.url)),'..');
export const upstreamRoot=path.join(root,'.local/upstream-katex');
const inside=file=>file===upstreamRoot||file.startsWith(upstreamRoot+path.sep);

registerHooks({
 resolve(specifier,context,nextResolve){
  if(specifier.startsWith('.')&&context.parentURL?.startsWith('file:')){
   const candidate=fileURLToPath(new URL(specifier,context.parentURL));
   if(inside(candidate)){
    for(const file of [candidate,candidate+'.ts',candidate+'.js',path.join(candidate,'index.ts')]){
     if(fs.existsSync(file)&&fs.statSync(file).isFile())return {url:pathToFileURL(file).href,shortCircuit:true};
    }
   }
  }
  return nextResolve(specifier,context);
 },
 load(url,context,nextLoad){
  if(url.startsWith('file:')){
   const file=fileURLToPath(url);
   if(inside(file)&&/\.(ts|js)$/.test(file)){
    const text=fs.readFileSync(file,'utf8');
    const format=file.endsWith('.js')&&text.includes('module.exports')?'commonjs':'module';
    return {format,source:file.endsWith('.ts')?stripTypeScriptTypes(text,{mode:'transform',sourceUrl:url}):text,shortCircuit:true};
   }
  }
  return nextLoad(url,context);
 }
});
globalThis.__VERSION__='0.18.11';

export async function sourceModule(relative){
 const file=path.resolve(upstreamRoot,relative);
 if(!inside(file))throw Error('Module outside locked upstream');
 return import(pathToFileURL(file).href);
}

if(process.argv[1]&&path.resolve(process.argv[1])===fileURLToPath(import.meta.url)){
 const source=await sourceModule('katex.ts');
 if(source.default.version!=='0.18.11')throw Error('Source version drift');
 process.stdout.write(JSON.stringify({version:source.default.version,exports:Object.keys(source.default),phase:'mechanical_source_import_only'})+'\n');
}
