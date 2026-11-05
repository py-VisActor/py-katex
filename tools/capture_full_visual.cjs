/* Locked official browser oracle; no installs, external requests or native B. */
const fs=require('node:fs'),path=require('node:path'),crypto=require('node:crypto');
const {createRequire}=require('node:module');
const root=path.resolve(__dirname,'..'),req=createRequire(path.join(root,'../py-mermaid/.local/f011-oracle/package.json'));
const arg=name=>process.argv[process.argv.indexOf(name)+1];
const sha=data=>crypto.createHash('sha256').update(data).digest('hex');
async function main(){
 const file=path.resolve(arg('--fixtures')),data=fs.readFileSync(file),fixture=JSON.parse(data),out=path.resolve(arg('--out'));
 fs.mkdirSync(out,{recursive:false});
 const source=path.join(root,'.local/katex-0.18.11/package'),info=JSON.parse(fs.readFileSync(path.join(source,'package.json'),'utf8'));
 if(info.version!=='0.18.11')throw Error('Official version drift');
 let css=fs.readFileSync(path.join(source,'dist/katex.min.css'),'utf8').replace(/@font-face\s*\{[^}]*\}/g,'');
 const fontInputs={};
 for(const name of fs.readdirSync(path.join(source,'dist/fonts')).filter(name=>name.endsWith('.ttf'))){
  const bytes=fs.readFileSync(path.join(source,'dist/fonts',name));fontInputs[name]=sha(bytes);
  const stem=name.slice(0,-4),split=stem.lastIndexOf('-'),family=stem.slice(0,split),face=stem.slice(split+1);
  css+=`@font-face{font-family:${family};font-style:${face.includes('Italic')?'italic':'normal'};font-weight:${face.includes('Bold')?700:400};src:url(data:font/ttf;base64,${bytes.toString('base64')}) format('truetype');}`;
 }
 const script=fs.readFileSync(path.join(source,'dist/katex.min.js'),'utf8');
 const browser=await req('playwright').chromium.launch({channel:'chrome',headless:true}),results=[];
 try{for(const item of fixture.cases){
  const page=await browser.newPage({viewport:{width:3200,height:2600},deviceScaleFactor:1});
  const externalRequests=[];await page.route('**/*',route=>{if(route.request().url().startsWith('data:'))return route.continue();externalRequests.push(route.request().url());return route.abort();});
  await page.setContent('<html><body style="margin:0;background:white"><div id="math" style="display:inline-block;position:absolute;left:512px;top:512px;white-space:nowrap"></div></body></html>');
  const size=item.options?.font_size??28,color=item.options?.color??'#000000';
  const equationCounter=item.options?.equation_counter??0;
  let extra=`.katex{font-size:${size}px!important}.katex-display{margin:0}#math{color:${color}}body{counter-reset:katexEqnNo ${equationCounter} mmlEqnNo ${equationCounter}}`;
  for(const [name,declarations] of Object.entries(item.htmlStyles||{}))extra+=`.${name.replace(/[^a-zA-Z0-9_-]/g,'\\$&')}{${declarations}}`;
  await page.addStyleTag({content:css+extra});await page.addScriptTag({content:script});
  const images={};
  for(const resource of item.resources||[]){
   const bytes=resource.path?fs.readFileSync(path.resolve(root,resource.path)):null;
   let uri=resource.dataUri;
   if(bytes){const ext=path.extname(resource.path).toLowerCase();const mime={'.png':'image/png','.svg':'image/svg+xml','.jpg':'image/jpeg','.jpeg':'image/jpeg','.gif':'image/gif','.webp':'image/webp'}[ext];if(!mime)throw Error('Unknown explicit oracle resource MIME');uri='data:'+mime+';base64,'+bytes.toString('base64');}
   images[resource.key]={uri,sha256:sha(bytes||Buffer.from(uri.split(',').slice(1).join(','),'base64'))};
  }
  const row={id:item.id,status:'ERROR',inputSha256:sha(Buffer.from(item.tex)),externalRequests,resources:Object.fromEntries(Object.entries(images).map(([key,value])=>[key,value.sha256]))};
  try{
   const state=await page.evaluate(async ({item,images})=>{
    const element=document.getElementById('math'),width=item.options?.content_width;
    if(width!=null){element.style.width=width+'px';element.style.whiteSpace='normal';}
    const options={displayMode:true,throwOnError:true,...(item.oracleOptions||{}),output:'htmlAndMathml'};
    element.innerHTML=katex.renderToString(item.tex,options);
    for(const image of element.querySelectorAll('img')){const key=image.getAttribute('src'),resource=images[key];if(resource)image.src=resource.uri;else if(!key.startsWith('data:image/'))throw Error('Undeclared source image '+key);await image.decode();}
    await document.fonts.ready;
    const visual=element.querySelector('.katex-html')||element;
    let visibleText='';const rectangles=[];const walker=document.createTreeWalker(visual,NodeFilter.SHOW_TEXT);
    while(walker.nextNode()){
     const node=walker.currentNode,parent=node.parentElement;let visible=true;
     for(let ancestor=parent;ancestor;ancestor=ancestor.parentElement){const style=getComputedStyle(ancestor);if(style.display==='none'||style.visibility==='hidden'||Number(style.opacity)===0){visible=false;break;}if(ancestor===element)break;}
     const paint=getComputedStyle(parent).color;if(/rgba\([^)]*,\s*0(?:\.0*)?\s*\)$/.test(paint)||paint==='transparent')visible=false;
     if(!visible)continue;
     const range=document.createRange();range.selectNodeContents(node);const box=range.getBoundingClientRect();
     if(!node.data.trim()||box.width===0&&box.height===0)continue;
     visibleText+=node.data;rectangles.push({text:node.data,left:box.left,top:box.top,right:box.right,bottom:box.bottom});
    }
    const bounds=[element.getBoundingClientRect(),...rectangles];
    for(const svg of visual.querySelectorAll('svg,img')){const box=svg.getBoundingClientRect();if(box.width&&box.height)bounds.push(box);}
    const minX=Math.min(...bounds.map(box=>box.left)),minY=Math.min(...bounds.map(box=>box.top)),maxX=Math.max(...bounds.map(box=>box.right)),maxY=Math.max(...bounds.map(box=>box.bottom));
    const autoTagCount=visual.querySelectorAll('.eqn-num').length;
    return {html:element.innerHTML,sourceTree:JSON.parse(JSON.stringify(katex.__parse(item.tex,{...options,macros:{...(item.oracleOptions?.macros||{})}}),(key,value)=>key==='loc'?undefined:value)),
      visibleText,rectangles,autoTagCount,expectedTagTexts:Array.from({length:autoTagCount},(_,index)=>'('+(index+1+(item.options?.equation_counter??0))+')'),
      clip:{x:Math.max(0,Math.floor(minX)-12),y:Math.max(0,Math.floor(minY)-12),width:Math.ceil(maxX)-Math.max(0,Math.floor(minX)-12)+12,height:Math.ceil(maxY)-Math.max(0,Math.floor(minY)-12)+12},
      sourceErrorRendered:element.querySelector('.katex-error')!==null};
   },{item,images});
   Object.assign(row,state,{status:'PASS'});
   await page.screenshot({path:path.join(out,item.id+'.png'),clip:state.clip,captureBeyondViewport:true});
   row.pngSha256=sha(fs.readFileSync(path.join(out,item.id+'.png')));
   if(externalRequests.length)throw Error('Oracle attempted external network');
  }catch(error){row.status='ERROR';row.error=String(error);}
  fs.writeFileSync(path.join(out,item.id+'.json'),JSON.stringify(row,null,2)+'\n');results.push({id:row.id,status:row.status,error:row.error,pngSha256:row.pngSha256});await page.close();
 }}finally{await browser.close();}
 const manifest={schema:'py-katex-full-official-visual/v1',version:info.version,inputSha:sha(data),inputSha256:sha(data),fixtures:file,fontInputs,cases:results,scope:'Static HTML visual branch, source host metadata retained in fixtures, no external requests'};
 fs.writeFileSync(path.join(out,'manifest.json'),JSON.stringify(manifest,null,2)+'\n');
 console.log(JSON.stringify({cases:results.length,errors:results.filter(row=>row.status!=='PASS')}));if(results.some(row=>row.status!=='PASS'))process.exitCode=1;
}
main().catch(error=>{console.error(error);process.exitCode=1});
