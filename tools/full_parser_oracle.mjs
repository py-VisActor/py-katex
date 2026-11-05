/* P3 development-only semantic oracle; P2 writes/checks syntax but never runs it. */
import fs from 'node:fs';
import path from 'node:path';
import crypto from 'node:crypto';
import {sourceModule,root} from './upstream_loader.mjs';

const argument=name=>process.argv[process.argv.indexOf(name)+1];
const fixtures=JSON.parse(fs.readFileSync(argument('--fixtures'),'utf8'));
const katex=(await sourceModule('katex.ts')).default;
const symbols=(await sourceModule('src/symbols.ts')).default;
const functions=(await sourceModule('src/defineFunction.ts'))._functions;
const environments=(await sourceModule('src/defineEnvironment.ts'))._environments;
const macros=(await sourceModule('src/defineMacro.ts'))._macros;
if(katex.version!=='0.18.11')throw Error('Fixed source version mismatch');
for(const [name,registry] of Object.entries({functions,environments,macros})){
 const expected=Object.keys(fixtures.coverage[name]).sort();
 if(JSON.stringify(expected)!==JSON.stringify(Object.keys(registry).sort()))throw Error('Source registry drift: '+name);
}

const childKeys=['body','base','numer','denom','index','sup','sub','below','label','fragment','tag'];
const atomTypes=new Set(['atom','mathord','textord']);
const featureMap={genfrac:'frac',sqrt:'sqrt',array:'array',includegraphics:'image',html:'html',tag:'tag',kern:'kern',rule:'rule',mathchoice:'mathchoice',font:'font',enclose:'enclose',smash:'smash',phantom:'phantom',vphantom:'phantom',reflectbox:'reflect',pmb:'pmb',spacing:'space',cr:'linebreak'};
function children(node){
 if(Array.isArray(node))return node;
 if(!node||typeof node!=='object')return [];
 if(node.type==='htmlmathml')return [node.html];
 if(node.type==='mathchoice')return [node.display,node.text,node.script,node.scriptscript];
 return childKeys.flatMap(key=>node[key]&&typeof node[key]==='object'?[node[key]]:[]);
}
function glyphs(node){
 if(!node)return '';
 if(Array.isArray(node))return node.map(glyphs).join('');
 if(atomTypes.has(node.type))return symbols[node.mode||'math']?.[node.text]?.replace||node.text||'';
 if(node.type==='op'&&node.name)return node.symbol?(symbols.math[node.name]?.replace||node.name):node.name.replace(/^\\/,'');
 if(node.type==='verb')return node.star?node.body.replace(/ /g,'\u2423'):node.body;
 let result=children(node).map(glyphs).join('');
 if(node.type==='array'&&node.tags)result+=node.tags.filter(Array.isArray).map(glyphs).join('');
 return result;
}
function semantics(tree){
 const features={};const arrays=[];const fractions=[];const images=[];const operators=[];const fonts=[];
 const visit=node=>{
  if(Array.isArray(node)){node.forEach(visit);return;}
  if(!node||typeof node!=='object')return;
  const feature=featureMap[node.type];if(feature)features[feature]=(features[feature]||0)+1;
  if(node.type==='array')arrays.push(node.body.map(row=>row.length));
  if(node.type==='font')fonts.push(node.font);
  if(node.type==='genfrac')fractions.push({bar:node.hasBarLine,style:node.size||'auto'});
  if(node.type==='op'||node.type==='operatorname')operators.push({glyphs:glyphs(node).replace(/\s/gu,''),symbol:Boolean(node.symbol),limits:Boolean(node.limits),alwaysHandle:Boolean(node.alwaysHandleSupSub),small:node.name==='\\smallint'});
  if(node.type==='includegraphics')images.push({src:node.src,alt:node.alt,width:node.width,height:node.height,totalheight:node.totalheight});
  children(node).forEach(visit);
  if(node.type==='array'&&node.tags)node.tags.filter(Array.isArray).forEach(visit);
 };
 visit(tree);
 return {glyphs:glyphs(tree).replace(/\s/gu,''),features,arrays,fractions,images,operators,fonts};
}

const original={log:console.log,warn:console.warn,error:console.error};
const results=[];
for(const item of fixtures.cases){
 const diagnostics=[];
 for(const key of Object.keys(original))console[key]=(...args)=>diagnostics.push({level:key,message:args.map(String).join(' ')});
 try{
  const settings={...item.settings,macros:{...(item.macros||{})},throwOnError:true};
  const tree=katex.__parse(item.tex,settings);
  results.push({id:item.id,accepted:true,semantics:semantics(tree),tree:JSON.parse(JSON.stringify(tree,(key,value)=>key==='loc'?undefined:value)),diagnostics});
 }catch(error){
  results.push({id:item.id,accepted:false,error:{name:error.name,message:error.message,position:error.position??null,length:error.length??null,rawMessage:error.rawMessage??null},diagnostics});
 }finally{Object.assign(console,original);}
}
const mismatches=results.filter(result=>result.accepted!==fixtures.cases.find(item=>item.id===result.id).expectedAccepted).map(result=>result.id);
const output={schema:'py-katex-full-parser-oracle/v1',version:katex.version,kind:'fixed_source_parser_semantics_no_canvas',fixtureSha256:crypto.createHash('sha256').update(fs.readFileSync(argument('--fixtures'))).digest('hex'),registry:{functions:Object.keys(functions).length,environments:Object.keys(environments).length,macros:Object.keys(macros).length},cases:results,unexpectedFixtureAcceptance:mismatches};
const destination=path.resolve(argument('--out'));fs.mkdirSync(path.dirname(destination),{recursive:true});fs.writeFileSync(destination,JSON.stringify(output,null,2)+'\n',{flag:'wx'});
original.log(JSON.stringify({output:destination,cases:results.length,unexpectedFixtureAcceptance:mismatches}));
if(mismatches.length)process.exitCode=1;
