const fs = require('node:fs');
const vm = require('node:vm');
const assert = require('node:assert/strict');
const path = require('node:path');
const root = path.basename(__dirname)==='tests' ? path.dirname(__dirname) : __dirname;
const html=fs.readFileSync(path.join(root,'dashboard_v4.html'),'utf8');
const source=html.slice(html.indexOf('  // O arquivo é preparado'),html.indexOf('  listarClientes().catch'));
function setup(){
  const nodes=new Map(); const downloads=[];const revoked=[];let next=0;
  const $=id=>{if(!nodes.has(id))nodes.set(id,{disabled:false,textContent:'',classList:{add(){},remove(){}},addEventListener(){}});return nodes.get(id)};
  const context=vm.createContext({$,document:{createElement:()=>({click(){downloads.push(this.download)},remove(){}}),body:{appendChild(){}}},window:{addEventListener(){}},URL:{createObjectURL:()=>`blob:${++next}`,revokeObjectURL:x=>revoked.push(x)},fetch:async()=>({ok:true,headers:{get:()=> 'application/pdf'},blob:async()=>({})})});
  vm.runInContext('let clienteId=1;'+source,context);
  return {context,$,downloads,revoked,run:s=>vm.runInContext(s,context)};
}
(async()=>{
  let t=setup();
  await t.run('prepararRelatorioPDF({}, {cliente_id:1, periodo:"08/2026"}, geracaoPDF)');
  assert.equal(t.$('#baixarPDF').disabled,false);t.$('#baixarPDF').onclick();assert.equal(t.downloads.length,1);
  t.run('limparRelatorioPDF(); clienteId=2');assert.deepEqual(t.revoked,['blob:1']);assert.equal(t.$('#baixarPDF').disabled,true);
  t.$('#baixarPDF').onclick();assert.equal(t.downloads.length,1);
  t=setup();let complete;t.context.fetch=()=>new Promise(r=>complete=r);
  const pending=t.run('prepararRelatorioPDF({}, {cliente_id:1,periodo:"08/2026"}, geracaoPDF)');
  t.run('limparRelatorioPDF(); clienteId=2');complete({ok:true,headers:{get:()=> 'application/pdf'},blob:async()=>({})});await pending;
  assert.equal(t.run('arquivoPDF'),null);assert.equal(t.$('#baixarPDF').disabled,true);
  t=setup();t.context.fetch=async()=>({ok:false,json:async()=>({detail:'Calcule novamente'})});
  await t.run('prepararRelatorioPDF({}, {cliente_id:1,periodo:"08/2026"}, geracaoPDF)');
  assert.equal(t.$('#estadoPDF').textContent,'Calcule novamente');assert.equal(t.run('arquivoPDF'),null);
  t=setup();await t.run('prepararRelatorioPDF({}, {cliente_id:2,periodo:"08/2026"}, geracaoPDF)');assert.equal(t.run('arquivoPDF'),null);
  console.log('PDF frontend: download, invalidation, late response, errors and client isolation passed');
})().catch(e=>{console.error(e);process.exitCode=1});
