/* Development-only locked KaTeX oracle. No installs, no external requests. */
const fs=require('node:fs'),path=require('node:path'),crypto=require('node:crypto');
const {createRequire}=require('node:module');
const root=path.resolve(__dirname,'..'),req=createRequire(path.join(root,'../py-mermaid/.local/f011-oracle/package.json'));
const arg=n=>process.argv[process.argv.indexOf(n)+1];
async function main(){
 const fixture=JSON.parse(fs.readFileSync(arg('--fixtures'),'utf8')),out=path.resolve(arg('--out'));fs.mkdirSync(out,{recursive:false});
 const up=path.join(root,'.local/katex-0.18.11/package');const info=JSON.parse(fs.readFileSync(path.join(up,'package.json'),'utf8'));if(info.version!=='0.18.11')throw Error('Oracle version drift');
 let css=fs.readFileSync(path.join(up,'dist/katex.min.css'),'utf8').replace(/@font-face\s*\{[^}]*\}/g,'');
 for(const name of fs.readdirSync(path.join(up,'dist/fonts')).filter(n=>n.endsWith('.ttf'))){const stem=name.slice(0,-4),split=stem.lastIndexOf('-'),family=stem.slice(0,split),style=stem.slice(split+1),data=fs.readFileSync(path.join(up,'dist/fonts',name)).toString('base64');css+=`@font-face{font-family:${family};font-style:${style.includes('Italic')?'italic':'normal'};font-weight:${style.includes('Bold')?700:400};src:url(data:font/ttf;base64,${data}) format('truetype');}`;}
 const browser=await req('playwright').chromium.launch({channel:'chrome',headless:true});const results=[];
 try{for(const item of fixture.cases){const page=await browser.newPage({viewport:{width:1600,height:1000},deviceScaleFactor:1});await page.route('**/*',route=>route.request().url().startsWith('data:')?route.continue():route.abort());
 await page.setContent('<html><head></head><body style="margin:0;background:white"><span id="math" style="display:inline-block;padding:10px"></span></body></html>');await page.addStyleTag({content:css+' .katex{font-size:28px!important}.katex-display{margin:0}'});await page.addScriptTag({content:fs.readFileSync(path.join(up,'dist/katex.min.js'),'utf8')});
 try{const data=await page.evaluate(item=>{const options={displayMode:item.display!==false,throwOnError:true,macros:item.macros||{},trust:false,output:'htmlAndMathml'};document.getElementById('math').innerHTML=katex.renderToString(item.tex,options);const tree=katex.__parse(item.tex,{...options,macros:{...(item.macros||{})}});return {tree:JSON.parse(JSON.stringify(tree,(k,v)=>k==='loc'?undefined:v)),html:document.getElementById('math').innerHTML};},item);await page.evaluate(()=>document.fonts.ready);await page.locator('#math').screenshot({path:path.join(out,item.id+'.png')});fs.writeFileSync(path.join(out,item.id+'.json'),JSON.stringify(data,null,2));results.push({id:item.id,status:'PASS'});}catch(e){const data={error:String(e)};fs.writeFileSync(path.join(out,item.id+'.json'),JSON.stringify(data));results.push({id:item.id,status:'FAIL',error:String(e)});}await page.close();}
 }finally{await browser.close();}
 fs.writeFileSync(path.join(out,'manifest.json'),JSON.stringify({version:info.version,sourceIntegrity:JSON.parse(fs.readFileSync(path.join(root,'references/upstream.lock.json'),'utf8')).npmIntegrity,cases:results},null,2));console.log(JSON.stringify({cases:results.length,failed:results.filter(x=>x.status!=='PASS')}));if(results.some(x=>x.status!=='PASS'))process.exitCode=1;
}
main().catch(e=>{console.error(e);process.exitCode=1});
