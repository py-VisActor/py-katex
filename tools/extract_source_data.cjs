/* Development only. Produce distributable constant data from pinned KaTeX. */
const fs=require('node:fs'),path=require('node:path'),vm=require('node:vm');
const {stripTypeScriptTypes}=require('node:module');
const root=path.resolve(__dirname,'..');
const source=path.join(root,'.local/katex-0.18.11/package/src');
const dest=path.join(root,'src/py_katex/data');fs.mkdirSync(dest,{recursive:true});
const read=name=>fs.readFileSync(path.join(source,name),'utf8');
const write=(name,value)=>fs.writeFileSync(path.join(dest,name+'.json'),JSON.stringify(value,null,2)+'\n');
const metricSource=read('fontMetricsData.js').replace('export default','');
const metrics=vm.runInNewContext('('+metricSource.trim().replace(/;$/,'')+')');write('font_metrics',metrics);
const globals=read('fontMetrics.ts');const start=globals.indexOf('= {',globals.indexOf('const sigmasAndXis'))+2;
const end=globals.indexOf('\n};',start)+2;write('global_metrics',vm.runInNewContext('('+globals.slice(start,end)+')'));
const symbols={math:{},text:{}};
vm.runInNewContext(read('symbols.ts').slice(read('symbols.ts').indexOf('const math =')).replace(/^export /gm,''),{
 defineSymbol:(mode,font,group,replace,name,unicode)=>{const value={font,group,replace};symbols[mode][name]=value;if(unicode&&replace)symbols[mode][replace]=value;}
});write('symbols',symbols);
const geometry=read('svgGeometry.ts');const ps=geometry.indexOf('= {',geometry.indexOf('export const path:'))+2,pe=geometry.indexOf('\n};',ps)+2;
write('svg_paths',vm.runInNewContext('('+geometry.slice(ps,pe)+')',{doubleBrushStroke:s=>s+' '+s}));
const literal={},dynamic=[];
const macroSource=stripTypeScriptTypes(read('macros.ts'),{mode:'transform'}).replace(/^import[\s\S]*?;\s*$/gm,'').replace(/^export default.*?;$/gm,'').replace(/^export /gm,'');
vm.runInNewContext(macroSource,{_macros:literal,defineMacro:(name,body)=>{if(typeof body==='string')literal[name]=body;else dynamic.push(name);},fontMetricsData:metrics,symbols,functions:{},makeEm:n=>n+'em',ParseError:Error});
write('macros',literal);write('dynamic_macros',dynamic);
function namesArrays(s){const result=[];for(const match of s.matchAll(/names:\s*\[/g)){const start=match.index+match[0].length-1;let depth=0,quote='',escaped=false,comment='';for(let i=start;i<s.length;i++){const c=s[i],n=s[i+1];if(comment==='line'){if(c==='\n')comment='';continue;}if(comment==='block'){if(c==='*'&&n==='/'){comment='';i++;}continue;}if(quote){if(escaped)escaped=false;else if(c==='\\')escaped=true;else if(c===quote)quote='';continue;}if(c==='/'&&n==='/'){comment='line';i++;continue;}if(c==='/'&&n==='*'){comment='block';i++;continue;}if(c==='"'||c==="'"||c==='`'){quote=c;continue;}if(c==='[')depth++;if(c===']'&&--depth===0){result.push(s.slice(start,i+1));break;}}}return result;}
const funcs=[];for(const folder of ['functions','environments']){if(!fs.existsSync(path.join(source,folder)))continue;for(const name of fs.readdirSync(path.join(source,folder))){if(!name.endsWith('.ts'))continue;const s=read(folder+'/'+name),names=[],unresolved=[];for(const array of namesArrays(s)){try{names.push(...vm.runInNewContext(array));}catch(error){unresolved.push(array);}}const macroNames=[...s.matchAll(/defineMacro\(\s*("(?:\\.|[^"\\])*"|'(?:\\.|[^'\\])*')/g)].map(m=>vm.runInNewContext(m[1]));funcs.push({source:'src/'+folder+'/'+name,category:folder,names,macroNames,unresolvedNameSources:unresolved});}}
fs.mkdirSync(path.join(root,'references'),{recursive:true});fs.writeFileSync(path.join(root,'references/function-inventory.json'),JSON.stringify({version:'0.18.11',functions:funcs,dynamicMacros:dynamic,literalMacroTableScope:'src/macros.ts only; function-local macro responsibilities are inventoried per file and may be native parser handlers'},null,2)+'\n');
console.log(JSON.stringify({fonts:Object.keys(metrics).length,symbols:Object.fromEntries(Object.entries(symbols).map(([k,v])=>[k,Object.keys(v).length])),literalMacros:Object.keys(literal).length,dynamicMacros:dynamic.length,functionFiles:funcs.length}));
