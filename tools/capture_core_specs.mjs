/* Development-only expression/decision capture from every locked core spec.
 * This is a functional corpus, NOT a claim that a Jest assertion suite was
 * translated or passed. Private markup assertions are inventoried separately.
 */
import fs from 'node:fs';
import path from 'node:path';
import crypto from 'node:crypto';
import util from 'node:util';
import {registerHooks,stripTypeScriptTypes} from 'node:module';
import {fileURLToPath} from 'node:url';
import {root,upstreamRoot,sourceModule} from './upstream_loader.mjs';

const arg=name=>process.argv[process.argv.indexOf(name)+1];
const out=path.resolve(arg('--out'));
const screenshotFixtures=JSON.parse(fs.readFileSync(arg('--screenshots'),'utf8'));
const katex=(await sourceModule('katex.ts')).default;
const parseTree=(await sourceModule('src/parseTree.ts')).default;
const Settings=(await sourceModule('src/Settings.ts')).default;
const sourceMacros=(await sourceModule('src/defineMacro.ts'))._macros;
const initialMacroDefinitions={...sourceMacros};
const originalConsole={warn:console.warn,log:console.log,error:console.error};
const r=value=>value&&typeof value==='object'&&'raw' in value?value.raw[0]:value;
const hash=value=>crypto.createHash('sha256').update(value).digest('hex');
const clauses=[],cases=[],pairs=[],suites=[];
const rootSuite={title:'',parent:null,children:[],beforeAll:[],afterAll:[],beforeEach:[],afterEach:[]};
let suite=rootSuite,current=null,sourceFile='',callIndex=0;

function scalar(value,seen=new Set()){
 if(value===undefined)return null;
 if(typeof value==='number'&&!Number.isFinite(value))return String(value);
 if(typeof value==='function')return {__callback:true,source:String(value)};
 if(value===null||typeof value!=='object')return value;
 if(value instanceof String)return String(value);
 if(seen.has(value))return {__cycle:true};
 seen.add(value);
 let result;
 if(Array.isArray(value))result=value.map(item=>scalar(item,seen));
 else result=Object.fromEntries(Object.entries(value).filter(([key])=>key!=='loc').map(([key,item])=>[key,scalar(item,seen)]));
 seen.delete(value);return result;
}

function capture(expression,settings,action,metadata={},invoke){
 if(!current)return invoke?invoke():parseTree(expression,new Settings(settings));
 const options=new Settings(settings),input=expression instanceof String?String(expression):expression;
 const exportedOptions=scalar(options);
 const extraMacros=Object.fromEntries(Object.entries(sourceMacros).filter(([name,definition])=>definition!==initialMacroDefinitions[name]));
 exportedOptions.macros={...scalar(extraMacros),...exportedOptions.macros};
 const row={id:'core-'+String(++callIndex).padStart(5,'0'),source:sourceFile,clause:current.id,title:current.title,
  action,tex:scalar(input),inputType:typeof input,options:exportedOptions,metadata,strictDecisions:[],trustDecisions:[],macroCalls:{},warnings:[]};
 const stableOptions={...options,macros:{...extraMacros,...options.macros}};
 for(const [name,definition] of Object.entries(stableOptions.macros)){
  if(typeof definition!=='function')continue;
  row.macroCalls[name]=[];
  stableOptions.macros[name]=context=>{
   const call={actions:[]};row.macroCalls[name].push(call);
   const proxy=new Proxy(context,{get(target,key){
    if(key==='macros')return new Proxy(target.macros,{get(namespace,method){const value=namespace[method];if(typeof value!=='function')return value;return (...args)=>{const result=value.apply(namespace,args);call.actions.push({method:'macros.'+String(method),args:scalar(args),result:scalar(result)});return result;};}});
    const value=target[key];if(typeof value!=='function')return value;
    return (...args)=>{const result=value.apply(target,args);call.actions.push({method:String(key),args:scalar(args),result:scalar(result)});return result;};
   }});
   try{const result=definition(proxy);call.result=scalar(result);return result;}
   catch(error){call.error=String(error);throw error;}
  };
 }
 for(const key of ['strict','trust']){
  if(typeof options[key]!=='function')continue;
  const callback=options[key];
  stableOptions[key]=(...args)=>{
   const entry={args:scalar(args)};
   try{entry.result=scalar(callback(...args));return entry.result;}
   catch(error){entry.error=String(error);throw error;}
   finally{row[key+'Decisions'].push(entry);}
  };
 }
 const prior=console.warn;console.warn=(...args)=>{row.warnings.push(args.map(String).join(' '));};
 cases.push(row);current.caseIds.push(row.id);
 try{
  const value=invoke?invoke(new Settings(stableOptions)):action==='parse'?parseTree(expression,new Settings(stableOptions)):katexOriginal.__renderToDomTree(expression,stableOptions);
  row.status=value?.classes?.includes('katex-error')||typeof value==='string'&&value.includes('class="katex-error"')?'ERROR_RENDERED':'ACCEPT';row.result=scalar(value);
  return value;
 }catch(error){row.status=error instanceof katex.ParseError?'REJECT':error instanceof TypeError&&typeof input!=='string'?'REJECT_INVALID_INPUT':'SOURCE_EXCEPTION';row.error={name:error.name,message:String(error),position:error.position??null,length:error.length??null,rawMessage:error.rawMessage??null};throw error;}
 finally{console.warn=prior;}
}

const katexOriginal=Object.fromEntries(Object.entries(katex));
for(const [name,action] of Object.entries({__parse:'parse',__renderToDomTree:'build',__renderToHTMLTree:'build',renderToString:'build'})){
 katex[name]=(expression,settings)=>capture(expression,settings,action,{origin:'katex.'+name},options=>katexOriginal[name](expression,options));
}

const collector={capture,r,
 getParsed:(expression,settings)=>capture(r(expression),settings,'parse',{origin:'getParsed'}),
 getBuilt:(expression,settings)=>{
  let node=capture(r(expression),settings,'build',{origin:'getBuilt'});
  if(node.classes?.includes('katex-error'))return node;
  if(node.classes?.includes('katex-display'))node=node.children[0];
  const html=node.children[1],children=[];
  for(const base of html.children)children.push(...(base.children||[]).filter(child=>!child.classes?.includes('katex-strut')));
  return children;
 },
 stripPositions:value=>scalar(value)
};
globalThis.__mathCoreCollector=collector;
registerHooks({
 load(url,context,nextLoad){
  if(!url.startsWith('file:'))return nextLoad(url,context);
  const file=fileURLToPath(url);
  if(file===path.join(upstreamRoot,'test/helpers.ts'))return {format:'module',shortCircuit:true,source:`
   import Settings from '../src/Settings';
   export const strictSettings=new Settings({strict:true}),nonstrictSettings=new Settings({strict:false}),trustSettings=new Settings({trust:true});
   export const r=globalThis.__mathCoreCollector.r,getParsed=globalThis.__mathCoreCollector.getParsed,getBuilt=globalThis.__mathCoreCollector.getBuilt,stripPositions=globalThis.__mathCoreCollector.stripPositions;
   export class ConsoleWarning extends Error{}
  `};
  if(file.startsWith(path.join(upstreamRoot,'test')+path.sep)&&file.endsWith('-spec.ts')){
   let source=fs.readFileSync(file,'utf8');
   source=source.replace(/import parseTreeOrig from ([^;]+);/,`import parseTreeActual from $1;const parseTreeOrig=(expression,settings)=>globalThis.__mathCoreCollector.capture(expression,settings,'parse',{origin:'direct_parseTree'},options=>parseTreeActual(expression,options));`);
   return {format:'module',source:stripTypeScriptTypes(source,{mode:'transform',sourceUrl:url}),shortCircuit:true};
  }
  return nextLoad(url,context);
 }
});

function describe(title,callback){const parent=suite,child={title:String(title),parent,children:[],beforeAll:[],afterAll:[],beforeEach:[],afterEach:[]};parent.children.push(child);suite=child;try{callback();}finally{suite=parent;}}
describe.only=describe;describe.skip=(title,callback)=>{const prior=suite;describe(title,callback);prior.children.at(-1).skip=true;};
function it(title,callback){const item={title:String(title),callback,parent:suite,source:sourceFile};suite.children.push(item);}
it.only=it;it.skip=(title,callback)=>{it(title,callback);suite.children.at(-1).skip=true;};it.todo=title=>it.skip(title,()=>{});
it.each=values=>(title,callback)=>{for(const value of values){const args=Array.isArray(value)?value:[value];it(util.format(title,...args),()=>callback(...args));}};
globalThis.describe=describe;globalThis.it=it;globalThis.test=it;
for(const kind of ['beforeAll','afterAll','beforeEach','afterEach'])globalThis[kind]=callback=>suite[kind].push(callback);
globalThis.require=specifier=>{if(specifier==='./screenshotter/ss_data.js')return screenshotFixtures.sourceItems;throw Error('Unsupported source-spec require '+specifier);};

function matcher(actual,negative=false){return new Proxy(function(){},{
 get(_target,name){
  if(name==='not')return matcher(actual,!negative);
  if(name==='then')return undefined;
  if(['toParse','toBuild','toWarn','toFailWithParseError'].includes(name))return (...args)=>{
   const settings=name==='toFailWithParseError'?args[1]:args[0];
   try{capture(r(actual),settings,name==='toBuild'||name==='toWarn'?'build':'parse',{origin:'expect.'+String(name),negative});}catch{}
  };
  if(['toParseLike','toBuildLike'].includes(name))return (expected,settings)=>{
   const action=name==='toParseLike'?'parse':'build',ids=[];
   for(const expression of [r(actual),r(expected)]){
    const index=cases.length;try{capture(expression,settings,action,{origin:'expect.'+String(name),negative});}catch{}
    if(cases.length>index)ids.push(cases.at(-1).id);
   }
   if(ids.length===2)pairs.push({left:ids[0],right:ids[1],action,expectedEquivalent:!negative,clause:current.id});
  };
  if(name==='toThrow'||name==='toThrowError')return ()=>{if(typeof actual==='function')try{actual();}catch{}};
  return ()=>undefined;
 },apply(){return undefined;}
});}
globalThis.expect=actual=>matcher(actual);
for(const name of ['any','anything','arrayContaining','objectContaining','stringContaining','stringMatching'])globalThis.expect[name]=value=>value;
globalThis.expect.extend=()=>{};globalThis.expect.addSnapshotSerializer=()=>{};
globalThis.fail=message=>{if(current)current.sourceProbeNotes.push(String(message));};
const spies=[];
function mock(implementation=()=>{}){
 let active=implementation;
 function fn(...args){fn.mock.calls.push(args);return active?.(...args);}
 fn.mock={calls:[]};fn.mockImplementation=next=>{active=next;return fn;};fn.mockReturnValue=value=>fn.mockImplementation(()=>value);fn.mockClear=()=>{fn.mock.calls=[];return fn;};fn.mockRestore=()=>{};return fn;
}
globalThis.jest={fn:mock,spyOn:(object,key)=>{const original=object[key],fn=mock((...args)=>original.apply(object,args));fn.mockRestore=()=>{object[key]=original;};object[key]=fn;spies.push(fn);return fn;},restoreAllMocks:()=>{while(spies.length)spies.pop().mockRestore();}};

const sourceSpecs=['test/katex-spec.ts','test/errors-spec.ts','test/unicode-spec.ts','test/mathml-spec.ts','test/dup-spec.ts','test/screenshotter-spec.ts'];
const sourceFiles={};
for(const relative of sourceSpecs){sourceFile=relative;sourceFiles[relative]=hash(fs.readFileSync(path.join(upstreamRoot,relative)));await sourceModule(relative);}

async function runSuite(group,ancestors=[]){
 const parents=[...ancestors,group];
 const skipGroup=parents.some(item=>item.skip)||parents.some(item=>item.title.includes('Extending katex by new fonts and symbols'));
 if(!skipGroup)for(const callback of group.beforeAll)await callback();
 for(const child of group.children){
  if(child.children){await runSuite(child,parents);continue;}
  const title=parents.map(item=>item.title).filter(Boolean).concat(child.title).join(' / ');
  sourceFile=child.source;current={id:'clause-'+String(clauses.length+1).padStart(4,'0'),source:sourceFile,title,caseIds:[],sourceProbeNotes:[],status:'COLLECTED'};clauses.push(current);
  const excluded=child.skip||parents.some(item=>item.skip)||title.includes('Extending katex by new fonts and symbols');
  if(excluded){current.status='EXCLUDED_SOURCE_SKIP_OR_JS_PRIVATE_EXTENSION';current=null;continue;}
  try{for(const parent of parents)for(const callback of parent.beforeEach)await callback();await child.callback();}
  catch(error){current.status='COLLECTOR_CALLBACK_EXCEPTION';current.error=String(error);}
  finally{for(const parent of [...parents].reverse())for(const callback of parent.afterEach)try{await callback();}catch(error){current.cleanupError=String(error);}globalThis.jest.restoreAllMocks();current=null;}
 }
 if(!skipGroup)for(const callback of group.afterAll)await callback();
}
await runSuite(rootSuite);
Object.assign(console,originalConsole);
fs.mkdirSync(out,{recursive:false});
const manifest={schema:'py-katex-core-source-corpus/v1',sourceVersion:'0.18.11',sourceFiles,sourceSpecs,clauses,cases,pairs,
 assertionScope:'Expression acceptance, rejection, strict/trust decisions and source equivalence inputs. This collector does not execute or assert the original Jest matchers; native semantic/pixel tests are separate.',
 summary:{clauses:clauses.length,cases:cases.length,pairs:pairs.length,callbackExceptions:clauses.filter(row=>row.status==='COLLECTOR_CALLBACK_EXCEPTION').map(row=>({id:row.id,title:row.title,error:row.error})),sourceExceptions:cases.filter(row=>row.status==='SOURCE_EXCEPTION').map(row=>({id:row.id,title:row.title,error:row.error})),classifications:Object.fromEntries([...new Set(cases.map(row=>row.status))].map(status=>[status,cases.filter(row=>row.status===status).length]))}};
fs.writeFileSync(path.join(out,'corpus.json'),JSON.stringify(manifest,null,2)+'\n');
console.log(JSON.stringify(manifest.summary));
