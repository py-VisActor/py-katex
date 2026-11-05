/* Mechanical registry capture from the locked source; no formula execution. */
import fs from 'node:fs';
import path from 'node:path';
import {sourceModule,root} from './upstream_loader.mjs';
const katex=(await sourceModule('katex.ts')).default;
const functions=(await sourceModule('src/defineFunction.ts'))._functions;
const environments=(await sourceModule('src/defineEnvironment.ts'))._environments;
const macros=(await sourceModule('src/defineMacro.ts'))._macros;
const data={version:katex.version,phase:'P1_mechanical_registry_only',
 functions:Object.fromEntries(Object.entries(functions).map(([name,spec])=>[name,
  Object.fromEntries(Object.entries(spec).filter(([key])=>!['handler','htmlBuilder','mathmlBuilder'].includes(key)))])),
 environments:Object.fromEntries(Object.entries(environments).map(([name,spec])=>[name,
  Object.fromEntries(Object.entries(spec).filter(([key])=>!['handler','htmlBuilder','mathmlBuilder'].includes(key)))])),
 macros:Object.fromEntries(Object.entries(macros).map(([name,definition])=>[name,
  typeof definition==='string'?{kind:'literal',expansion:definition}:{kind:typeof definition}]))};
const out=path.join(root,'references/full-runtime-registry.json');
fs.writeFileSync(out,JSON.stringify(data,null,2)+'\n');
process.stdout.write(JSON.stringify({functions:Object.keys(data.functions).length,environments:Object.keys(data.environments).length,macros:Object.keys(data.macros).length,literal:Object.values(data.macros).filter(x=>x.kind==='literal').length})+'\n');
