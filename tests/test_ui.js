// Independent JS/DOM-stub checks only; no claim of Windows GUI validation.
const fs=require('fs'),path=require('path'),vm=require('vm'),assert=require('assert');
const file=path.join(__dirname,'../ui.html'),html=fs.readFileSync(file,'utf8');
const js=html.match(/<script>([\s\S]*?)<\/script>/)[1];new vm.Script(js);
const ids=[...html.matchAll(/\bid="([^"]+)"/g)].map(m=>m[1]);assert.equal(new Set(ids).size,ids.length,'duplicate IDs');
const refs=[...js.matchAll(/\$\('([^']+)'\)/g)].map(m=>m[1]);for(const id of refs)assert(ids.includes(id),'missing DOM ID '+id);
assert(!/\/api\/preview|previewSelect|loadPreview|updatePreviews|beforeImg|afterImg|wipeRange/.test(js));
assert(!/id="(?:previewSelect|beforeImg|afterImg|compareStage|wipeRange)"/.test(html));
assert(html.includes('v0.1.1'));assert(html.includes('/api/open-logs'));
function element(){return {style:{},children:[],classList:{add(){},remove(){},toggle(){}},setAttribute(k,v){this[k]=v},appendChild(e){this.children.push(e)},append(...e){this.children.push(...e)},replaceChildren(...e){this.children=e},addEventListener(){},set innerHTML(v){throw Error('HTML injection')}};}
const nodes=new Map(ids.map(id=>[id,element()]));const $=id=>{assert(nodes.has(id),'missing '+id);return nodes.get(id)};
const context={$: $,state:{status:'idle',items:[],logs:'',output:'',log_warning:''},labels:{complete:'完成',running:'运行中'},rowLabels:{done:'完成',error:'失败'},busy:false,stopped:false,connected:true,cancelPending:false,listing:'status',lastAlert:'',tableSignature:'',isRunning(){return context.state.status==='running'},showError(){},document:{querySelectorAll(){return []},createElement:element,createDocumentFragment:element},console};
const names=['setControls','canonicalStatus','rowClass','dimensions','duration','renderTable','progressPercent','updateState'];const code=js.split('\n').filter(l=>names.some(n=>l.startsWith('function '+n+'('))).join('\n');assert.equal(code.split('\n').length,names.length);vm.createContext(context);vm.runInContext(code,context);
context.updateState({status:'complete',total:2,done:2,failed:1,progress:100,output:'C:/results/run1',logs:'C:/tool/logs/run1',items:[{name:'<svg onload=alert(1)>.png',output:'角色/a.png_AI.png',source_width:64,source_height:32,width:128,height:64,seconds:1.2,status:'done'},{name:'bad.png',status:'error',error:'<script>bad</script>'}]});
assert.equal($('openOutputBtn').disabled,false);assert.equal($('openLogsBtn').disabled,false);assert.equal($('progressCount').textContent,'2 / 2');assert.equal($('listSummary').textContent,'成功 1 · 失败 1');
assert.equal($('logsLocation').textContent,'报告位置：C:/tool/logs/run1');assert.equal(context.dimensions(context.state.items[0]),'64 × 32 → 128 × 64');
const row=$('fileRows').children[0].children[0];assert.equal(row.children[0].children[0].textContent,'<svg onload=alert(1)>.png');assert.equal(row.children[0].children[1].textContent,'成品：角色/a.png_AI.png');
context.updateState({status:'complete',logs:'',log_warning:'日志不可写',items:[]});assert.equal($('openLogsBtn').disabled,true);assert.equal($('logsDescription').textContent,'日志不可写');assert.equal($('openOutputBtn').disabled,false);
context.updateState({status:'running',output:'',logs:'',log_warning:'',total:0,done:0,failed:0,items:[]});assert.equal($('openOutputBtn').disabled,true);assert.equal($('openLogsBtn').disabled,true);assert.equal($('logsLocation').hidden,true);assert.equal(context.progressPercent({status:'running',total:1000,done:1,progress:.1}),.1);
console.log('PASS: full JS parse; '+ids.length+' unique IDs; no preview code/routes; result rows, dimensions, escaping, report controls, warnings, repeat-run reset, progress');
