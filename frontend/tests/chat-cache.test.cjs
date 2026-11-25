const assert=require('node:assert/strict');
const {readFileSync}=require('node:fs');
const {join}=require('node:path');
const {test}=require('node:test');
const vm=require('node:vm');
const ts=require('typescript');

function cache() {
  let data={};let fail=false;
  const clone=x=>JSON.parse(JSON.stringify(x));
  const browser={storage:{session:{
    get:async key=>clone({[key]:data[key]??null}),
    set:async values=>{if(fail)throw Error('storage unavailable');data={...data,...clone(values)};},
    remove:async key=>{delete data[key];},
  }}};
  const code=ts.transpileModule(readFileSync(join(__dirname,'../services/chatCache.ts'),'utf8'),{
    compilerOptions:{module:ts.ModuleKind.CommonJS,target:ts.ScriptTarget.ES2022},
  }).outputText;
  const module={exports:{}};
  vm.runInNewContext(code,{module,exports:module.exports,require:()=>({browser})});
  return{...module.exports,fail:value=>{fail=value;}};
}
function draft(changes={}) {
  return{messages:[{sender:'user',text:'Which forms?'},{sender:'bot',text:'A cited answer',sources:[]}],
    input:'A draft follow-up',context:null,followUp:null,interrupted:false,...changes};
}

test('reopening restores messages and draft input from browser-session storage',async()=>{
  const c=cache();await c.saveChatDraft('user-a:approved',draft());
  const restored=await c.loadChatDraft('user-a:approved');
  assert.equal(restored.messages.length,2);assert.equal(restored.input,'A draft follow-up');
});

test('another account or permission scope cannot restore a conversation',async()=>{
  const c=cache();await c.saveChatDraft('user-a:approved:internal',draft());
  assert.equal(await c.loadChatDraft('user-b:approved:internal'),null);
  assert.equal(await c.loadChatDraft('user-a:approved:none'),null);
});

test('cart restoration preserves funding but invalidates live-cart confirmation',async()=>{
  const c=cache();const context={cart:{reviewed:true,items:[]},suppliers:[{supplier:'A',funding:'federal_grant'}],pending_question:null,last_question:'What forms?'};
  await c.saveChatDraft('a',draft({context}));
  const restored=await c.loadChatDraft('a');
  assert.equal(restored.context.cart.reviewed,false);
  assert.equal(restored.context.suppliers[0].funding,'federal_grant');
  assert.equal(restored.context.pending_question,'What forms?');
  assert.equal(context.cart.reviewed,true);
});

test('logout clear invalidates queued writes and removes the cached conversation',async()=>{
  const c=cache();await c.saveChatDraft('a',draft());
  const saving=c.saveChatDraft('a',draft({input:'Late write'}));
  const clearing=c.clearChatDraft();await Promise.all([saving,clearing]);
  assert.equal(await c.loadChatDraft('a'),null);
});

test('cache writes are frozen and serialized in order',async()=>{
  const c=cache();const first=draft({input:'First'});const saving=c.saveChatDraft('a',first);first.input='Mutated';
  await saving;assert.equal((await c.loadChatDraft('a')).input,'First');
  await Promise.all([c.saveChatDraft('a',draft({input:'Second'})),c.saveChatDraft('a',draft({input:'Last'}))]);
  assert.equal((await c.loadChatDraft('a')).input,'Last');
});

test('a failed storage write does not poison later saves',async()=>{
  const c=cache();c.fail(true);await assert.rejects(c.saveChatDraft('a',draft()),/storage unavailable/);
  c.fail(false);await c.saveChatDraft('a',draft());assert.equal((await c.loadChatDraft('a')).messages.length,2);
});

test('an interrupted request is retained for a retry rather than fabricated as answered',async()=>{
  const c=cache();await c.saveChatDraft('a',draft({messages:[{sender:'user',text:'Unanswered question'}],input:'',interrupted:true}));
  const restored=await c.loadChatDraft('a');
  assert.equal(restored.interrupted,true);assert.equal(restored.messages.length,1);assert.equal(restored.messages[0].sender,'user');
});
