const fs=require('node:fs'),vm=require('node:vm'),assert=require('node:assert/strict'),path=require('node:path');
const html=fs.readFileSync(path.join(__dirname,'dashboard_v4.html'),'utf8');
const source=html.slice(html.indexOf('  let versaoCadastrosPDF=0;'),html.indexOf('  listarClientes().catch'));
function setup(){
 const nodes=new Map(),downloads=[];
 const $=s=>{if(!nodes.has(s))nodes.set(s,{value:s.includes('cbs')?'0.088':'0.001',disabled:false,textContent:''});return nodes.get(s)};
 const ctx=vm.createContext({$,URLSearchParams,setTimeout:fn=>fn(),URL:{createObjectURL:()=> 'blob:test',revokeObjectURL(){}},document:{body:{appendChild(){}},createElement:()=>({click(){downloads.push(this.download)},remove(){}})},fetch:async()=>({ok:true,headers:{get:()=> 'application/pdf'},blob:async()=>({})})});
 vm.runInContext('let clienteId=1;'+source,ctx);return {ctx,$,downloads};
}
(async()=>{
 let t=setup();await t.$('#baixarCadastrosPDF').onclick();assert.deepEqual(t.downloads,['clientes-fornecedores-1.pdf']);assert.equal(t.$('#baixarCadastrosPDF').disabled,false);
 t=setup();let resolve;t.ctx.fetch=()=>new Promise(r=>resolve=r);const pending=t.$('#baixarCadastrosPDF').onclick();vm.runInContext('cancelarRelatorioCadastros();clienteId=2',t.ctx);resolve({ok:true,headers:{get:()=> 'application/pdf'},blob:async()=>({})});await pending;assert.equal(t.downloads.length,0);
 t=setup();t.ctx.fetch=async()=>({ok:false,json:async()=>({detail:'Sem cadastros'})});await t.$('#baixarCadastrosPDF').onclick();assert.equal(t.downloads.length,0);assert.equal(t.$('#estadoCadastrosPDF').textContent,'Sem cadastros');assert.equal(t.$('#baixarCadastrosPDF').disabled,false);
 console.log('PDF cadastros: download, resposta atrasada e recuperação de erro OK');
})().catch(e=>{console.error(e);process.exitCode=1});
