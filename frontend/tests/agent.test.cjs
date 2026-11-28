const assert = require('node:assert/strict');
const {readFileSync} = require('node:fs');
const {join} = require('node:path');
const {test} = require('node:test');
const vm = require('node:vm');
const ts = require('typescript');

function service(fetch) {
  const code = ts.transpileModule(readFileSync(join(__dirname,'../services/agent.ts'),'utf8'),{
    compilerOptions:{module:ts.ModuleKind.CommonJS,target:ts.ScriptTarget.ES2022},
  }).outputText;
  const module={exports:{}};
  vm.runInNewContext(code,{module,exports:module.exports,URL,AbortSignal,fetch,
    require:()=>({API_BASE_URL:'http://localhost:8000',getFreshIdToken:async()=> 'fresh',SessionError:Error})});
  return module.exports;
}

test('citation links use verified HTTPS URLs and actual PDF pages',()=>{
  const {citationUrl}=service();
  assert.equal(citationUrl({source_url:'https://official.example/policy.pdf',page:'3-5'}),'https://official.example/policy.pdf#page=3');
  assert.equal(citationUrl({source_url:'https://official.example/doc/policy',page:'3'}),'https://official.example/doc/policy');
  for (const url of ['javascript:alert(1)','http://example.test/policy.pdf','file:///secret','invalid',null])
    assert.equal(citationUrl({source_url:url,page:'3'}),undefined);
});

function chatHelpers() {
  const code=ts.transpileModule(readFileSync(join(__dirname,'../services/chat.ts'),'utf8'),{
    compilerOptions:{module:ts.ModuleKind.CommonJS,target:ts.ScriptTarget.ES2022},
  }).outputText;
  const module={exports:{}};
  vm.runInNewContext(code,{module,exports:module.exports,Date});
  return module.exports;
}

function chatFixture(options={}) {
  const values=[],effects=[],refs=[];
  let cursor=0,refCursor=0,effectCursor=0;
  let auth={userProfile:{uid:'user-a',clearance:'internal'},isAuthenticated:true,isApproved:true,isLoading:false,refreshSession:async()=>{}};
  let resolve,resolveCart;
  const pending=new Promise(r=>{resolve=r;});
  const pendingCart=new Promise(r=>{resolveCart=r;});
  const calls=[];let captures=0;
  const react={
    createElement:(type,props,...children)=>({type,props:{...props,children}}),
    useState:(initial)=>{const i=cursor++;if(!(i in values))values[i]=initial;return[values[i],value=>{values[i]=typeof value==='function'?value(values[i]):value;}];},
    useRef:(initial)=>{const i=refCursor++;return refs[i]??(refs[i]={current:initial});},
    useEffect:(callback,deps)=>{const i=effectCursor++;if(!effects[i]||deps.some((d,n)=>d!==effects[i][n])){effects[i]=deps;callback();}},
  };
  const code=ts.transpileModule(readFileSync(join(__dirname,'../components/pages/ChatPage.tsx'),'utf8'),{
    compilerOptions:{module:ts.ModuleKind.CommonJS,target:ts.ScriptTarget.ES2022,jsx:ts.JsxEmit.React,esModuleInterop:true},
  }).outputText;
  const module={exports:{}};
  vm.runInNewContext(code,{module,exports:module.exports,Error,require:(name)=>{
    if(name==='react')return react;
    if(name.endsWith('AuthContext'))return{useAuth:()=>auth};
    if(name.endsWith('Login'))return{default:()=>null};
    if(name.endsWith('services/agent'))return{askQuestion:(...args)=>{calls.push(args);return options.ask?options.ask(...args):pending;},citationUrl:()=>undefined};
    if(name.endsWith('services/cart'))return{captureCart:()=>{captures++;return options.capture?options.capture():pendingCart;}};
    if(name.endsWith('services/chat'))return chatHelpers();
    if(name.endsWith('services/chatCache'))return{
      loadChatDraft:()=>({then(callback){callback(options.draft??null);return{catch(){}};}}),
      saveChatDraft:async()=>{},clearChatDraft:async()=>{},
    };
    if(name.endsWith('ChatCartPanel'))return{ChatCartPanel:function ChatCartPanel(){}};
    if(name.endsWith('ChatAnswerText'))return{ChatAnswerText:function ChatAnswerText(){}};
    if(name.endsWith('services/auth'))return{SessionError:Error};
    throw Error(name);
  }});
  return {values,resolve,resolveCart,calls,captureCount:()=>captures,render:()=>{cursor=0;refCursor=0;effectCursor=0;return module.exports.ChatPage();},
    changeSession:changes=>{auth={...auth,...changes};}};
}
function find(tree,type){
  if(!tree||typeof tree!=='object')return;
  if(tree.type===type)return tree;
  for(const child of (tree.props?.children??[]).flat(Infinity)){
    const match=find(child,type);if(match)return match;
  }
}

for(const change of ['sign out','account change','clearance reduction']) {
  test(`chat clears history and rejects an in-flight answer after ${change}`,async()=>{
    const f=chatFixture();
    f.render();
    find(f.render(),'input').props.onChange({target:{value:'Pricing question'}});
    const sending=find(f.render(),'form').props.onSubmit({preventDefault(){}});
    assert.equal(f.values[1].length,1);
    if(change==='sign out')f.changeSession({isAuthenticated:false,isApproved:false,userProfile:null});
    if(change==='account change')f.changeSession({userProfile:{uid:'user-b',clearance:'internal'}});
    if(change==='clearance reduction')f.changeSession({userProfile:{uid:'user-a',clearance:'none'}});
    f.render();
    assert.equal(f.values[1].length,0);
    f.resolve({answer:'Private answer from the previous session',sources:[]});
    await sending;
    assert.equal(f.values[1].length,0);
  });
}

test('logging back into the same account cannot restore a pre-logout answer',async()=>{
  const f=chatFixture();f.render();
  find(f.render(),'input').props.onChange({target:{value:'Pricing question'}});
  const sending=find(f.render(),'form').props.onSubmit({preventDefault(){}});
  f.changeSession({isAuthenticated:false,isApproved:false,userProfile:null});f.render();
  f.changeSession({isAuthenticated:true,isApproved:true,userProfile:{uid:'user-a',clearance:'internal'}});f.render();
  f.resolve({answer:'Pre-logout answer',sources:[]});await sending;
  assert.equal(f.values[1].length,0);
});

function snapshot(multiple=false) {
  const item={description:'Lab supplies',supplier:'Supplier A',quantity:'1',unit_price:'30.00',line_total:'30.00'};
  return {items:multiple?[item,{...item,supplier:'Supplier B'}]:[item],currency:'USD',subtotal:multiple?'60.00':'30.00',tax:'0.00',shipping:null,handling:null,total:multiple?'60.00':'30.00'};
}
function all(tree,predicate) {
  if(!tree||typeof tree!=='object')return[];
  return [...(predicate(tree)?[tree]:[]),...(tree.props?.children??[]).flat(Infinity).flatMap(child=>all(child,predicate))];
}
function button(tree,text) {
  return all(tree,node=>node.type==='button').find(node=>JSON.stringify(node.props.children).includes(text));
}
function panel(tree) {
  return all(tree,node=>typeof node.type==='function'&&node.type.name==='ChatCartPanel')[0];
}

test('fresh cart capture is usable without checkbox approval and funding stays unknown',()=>{
  const {attachCart}=chatHelpers();const first=attachCart(snapshot());
  assert.equal(first.cart.reviewed,true);assert.equal(first.independent_purchases,false);
  assert.equal(first.suppliers[0].funding,'unknown');assert.equal(first.suppliers[0].shipping,null);
  const multiple=attachCart(snapshot(true));assert.equal(multiple.suppliers.length,2);
  assert.ok(multiple.suppliers.every(s=>s.tax===null&&s.shipping===null&&s.funding==='unknown'));
});

test('history is bounded and cannot create system-role messages',()=>{
  const history=chatHelpers().recentHistory(Array.from({length:12},(_,i)=>({sender:i%2?'bot':'user',text:'x'.repeat(5000)})));
  assert.equal(history.length,8);assert.ok(history.every(t=>['user','assistant'].includes(t.role)&&t.content.length===4000));
});

test('chat transport sends fresh auth plus structured context and history',async()=>{
  let request;const {askQuestion}=service(async(url,options)=>{request={url,...options};return{ok:true,json:async()=>({answer:'OK',sources:[]})};});
  await askQuestion('What forms?',chatHelpers().attachCart(snapshot(true)),[{role:'user',content:'Earlier question'}]);
  const body=JSON.parse(request.body);assert.equal(request.headers.Authorization,'Bearer fresh');
  assert.equal(body.chat_context.suppliers.length,2);assert.equal(body.history[0].content,'Earlier question');
});

function toolFixture(extra={}) {
  let requests=0;
  return chatFixture({...extra,ask:extra.ask??(async(question,purchase)=>++requests===1
    ?{answer:'Reading cart',sources:[],tool_request:{name:'read_cart',question:'What forms do I need for my cart?'}}
    :{answer:'Are these separate goods purchases?',sources:[],chat_context:purchase,follow_up:{kind:'scope',supplier:null,choices:[{label:'Yes',value:'Yes'}]}})});
}
function send(f,text) {
  find(f.render(),'input').props.onChange({target:{value:text}});
  return find(f.render(),'form').props.onSubmit({preventDefault(){}});
}

test('a chat question executes the cart tool automatically and resumes the request',async()=>{
  const f=toolFixture();f.render();const sending=send(f,'What forms do I need for my cart?');
  f.resolveCart(snapshot(true));await sending;
  assert.equal(f.captureCount(),1);assert.equal(f.calls.length,2);
  assert.equal(f.calls[1][1].cart.reviewed,true);assert.equal(f.calls[1][1].suppliers.length,2);
  assert.equal(f.values[1].filter(m=>m.sender==='user').length,1);
  assert.equal(f.values[7].kind,'scope');
});

test('an ordinary policy question does not scrape the cart',async()=>{
  const f=chatFixture({ask:async()=>({answer:'Definition',sources:[]})});f.render();await send(f,'What is an SSPR?');
  assert.equal(f.captureCount(),0);assert.equal(f.calls.length,1);
});

test('funding choices are answered in chat with the pending purchase context',async()=>{
  const f=chatFixture({ask:async(question,purchase)=>({answer:'What funding?',sources:[],chat_context:{...purchase,pending_question:'What forms?'},follow_up:{kind:'funding',supplier:'Supplier A',choices:[{label:'Federal funds',value:'Federal funds'}]}})});
  f.render();f.values[6]=chatHelpers().attachCart(snapshot());await send(f,'What forms?');
  await button(f.render(),'Federal funds').props.onClick();
  assert.equal(f.calls.length,1);
  assert.equal(f.values[2],'Federal funds');
  await find(f.render(),'form').props.onSubmit({preventDefault(){}});
  assert.equal(f.calls[1][0],'Federal funds');assert.equal(f.calls[1][1].pending_question,'What forms?');
});

for(const change of ['sign out','account change']) {
  test(`cart tool cannot restore data after ${change}`,async()=>{
    const f=toolFixture();f.render();const sending=send(f,'What forms for my cart?');
    await Promise.resolve();
    f.changeSession(change==='sign out'?{isAuthenticated:false,isApproved:false,userProfile:null}:{userProfile:{uid:'user-b',clearance:'internal'}});
    f.render();f.resolveCart(snapshot());await sending;
    assert.equal(f.values[6],null);assert.equal(f.values[1].length,0);assert.equal(f.calls.length,1);
  });
}

test('removing cart resets its context and rejects a stale answer',async()=>{
  const f=chatFixture();f.render();f.values[6]=chatHelpers().attachCart(snapshot());
  const sending=send(f,'What forms?');panel(f.render()).props.onClear();
  f.resolve({answer:'Stale answer',sources:[],chat_context:chatHelpers().attachCart(snapshot())});await sending;
  assert.equal(f.values[6],null);assert.equal(f.values[1].length,0);
});

test('a failed read clears old cart context and reports how to retry',async()=>{
  const f=toolFixture({capture:async()=>{throw Error('Open the CruzBuy Simple Cart');}});f.render();f.values[6]=chatHelpers().attachCart(snapshot());
  await send(f,'Refresh my cart');assert.equal(f.values[6],null);assert.match(f.values[5],/Open the CruzBuy/);
});

test('only read_cart is an allowed browser tool',async()=>{
  const f=toolFixture({ask:async()=>({answer:'',sources:[],tool_request:{name:'submit_order',question:'Cart'}})});f.render();
  await send(f,'Check my cart');assert.equal(f.captureCount(),0);assert.match(f.values[5],/Unsupported assistant tool/);
});

test('tool requests cannot create an unbounded scraping loop',async()=>{
  const f=toolFixture({ask:async()=>({answer:'',sources:[],tool_request:{name:'read_cart',question:'Cart'}})});f.render();
  const sending=send(f,'Check my cart');f.resolveCart(snapshot());await sending;
  assert.equal(f.captureCount(),1);assert.equal(f.calls.length,2);assert.match(f.values[5],/Could not finish/);
});

test('refresh preserves funding only when the captured cart is unchanged',()=>{
  const {attachCart}=chatHelpers();const old=attachCart(snapshot());old.suppliers[0].funding='federal_grant';old.independent_purchases=true;
  const same=attachCart(snapshot(),old);assert.equal(same.suppliers[0].funding,'federal_grant');assert.equal(same.independent_purchases,true);
  const changed=attachCart(snapshot(true),old);assert.equal(changed.independent_purchases,false);assert.ok(changed.suppliers.every(s=>s.funding==='unknown'));
});

test('reopening restores messages and automatically refreshes a stale cart on demand',async()=>{
  const context=chatHelpers().attachCart(snapshot());context.cart.reviewed=false;
  const f=toolFixture({draft:{messages:[{sender:'user',text:'Earlier question'},{sender:'bot',text:'Earlier answer',sources:[]}],input:'',context,followUp:null,interrupted:false}});
  f.render();const sending=send(f,'What forms for my cart?');f.resolveCart(snapshot());await sending;
  assert.equal(f.values[1][0].text,'Earlier question');assert.equal(f.values[6].cart.reviewed,true);assert.equal(f.captureCount(),1);
});

test('restored interrupted requests are offered for retry, not stuck sending',()=>{
  const f=chatFixture({draft:{messages:[{sender:'user',text:'Unanswered question'}],input:'',context:null,followUp:null,interrupted:true}});
  f.render();f.render();assert.equal(f.values[2],'Unanswered question');assert.equal(f.values[4],false);
});

test('cart panel is read-only: no dropdowns, checkboxes or charge-entry form',()=>{
  const module={exports:{}};const code=ts.transpileModule(readFileSync(join(__dirname,'../components/ChatCartPanel.tsx'),'utf8'),{
    compilerOptions:{module:ts.ModuleKind.CommonJS,target:ts.ScriptTarget.ES2022,jsx:ts.JsxEmit.React,esModuleInterop:true},
  }).outputText;
  vm.runInNewContext(code,{module,exports:module.exports,Date,require:()=>({createElement:(type,props,...children)=>({type,props:{...props,children}})})});
  const tree=module.exports.ChatCartPanel({context:chatHelpers().attachCart(snapshot()),disabled:false,onRefresh(){},onClear(){}});
  assert.equal(all(tree,node=>['select','input','form'].includes(node.type)).length,0);
});

test('multiple-choice replies can be edited before sending',async()=>{
  const f=chatFixture({ask:async(question,purchase)=>({answer:'Which funding?',sources:[],chat_context:purchase,follow_up:{kind:'funding',supplier:'Supplier A',choices:[{label:'Federal funds',value:'Federal funds'},{label:'Non-federal funds',value:'Non-federal funds'}]}})});
  f.render();f.values[6]=chatHelpers().attachCart(snapshot());await send(f,'What forms?');
  const tree=f.render();assert.equal(all(tree,n=>n.props?.role==='group'&&n.props['aria-label']==='Choose a reply').length,1);
  button(tree,'Federal funds').props.onClick();
  assert.equal(button(f.render(),'Federal funds').props['aria-pressed'],true);
  find(f.render(),'input').props.onChange({target:{value:'Federal grant'}});
  assert.equal(button(f.render(),'Federal funds').props['aria-pressed'],false);
  assert.equal(f.calls.length,1);
  await find(f.render(),'form').props.onSubmit({preventDefault(){}});
  assert.equal(f.calls[1][0],'Federal grant');
});

test('amount questions use typed replies without suggested amount buttons',async()=>{
  const f=chatFixture({ask:async(question,purchase)=>({answer:'What is estimated shipping?',sources:[],chat_context:purchase,follow_up:{kind:'charges',supplier:'Supplier A',choices:[]}})});
  f.render();f.values[6]=chatHelpers().attachCart(snapshot());await send(f,'What forms?');
  const tree=f.render();assert.equal(all(tree,n=>n.props?.role==='group').length,0);
  assert.match(find(tree,'input').props.placeholder,/amount in USD/);
  assert.equal(find(tree,'input').props.inputMode,'decimal');
  await send(f,'5.00');assert.equal(f.calls[1][0],'5.00');
});

test('only the latest question exposes its reply buttons',async()=>{
  let count=0;
  const f=chatFixture({ask:async(question,purchase)=>++count===1
    ?{answer:'Which funding?',sources:[],chat_context:purchase,follow_up:{kind:'funding',supplier:'Supplier A',choices:[{label:'Federal funds',value:'Federal funds'}]}}
    :{answer:'Which award?',sources:[],chat_context:purchase,follow_up:{kind:'award_type',supplier:'Supplier A',choices:[{label:'Federal grant',value:'Federal grant'}]}}});
  f.render();f.values[6]=chatHelpers().attachCart(snapshot());await send(f,'What forms?');
  button(f.render(),'Federal funds').props.onClick();await find(f.render(),'form').props.onSubmit({preventDefault(){}});
  const tree=f.render();assert.equal(button(tree,'Federal funds'),undefined);assert.ok(button(tree,'Federal grant'));
  assert.equal(all(tree,n=>n.props?.role==='group').length,1);
});

test('rapid repeated submissions cannot send the selected answer twice',async()=>{
  const f=chatFixture();f.render();find(f.render(),'input').props.onChange({target:{value:'Federal grant'}});
  const submit=find(f.render(),'form').props.onSubmit;
  const first=submit({preventDefault(){}});const second=submit({preventDefault(){}});
  assert.equal(f.calls.length,1);f.resolve({answer:'Next question',sources:[]});await Promise.all([first,second]);
});

test('chat defaults to the short answer and preserves full detail and form links',async()=>{
  const links=[{title:'SSPR form',url:'https://financial.ucsc.edu/form.pdf',aliases:['SSPR']}];
  const f=chatFixture({ask:async()=>({answer:'Long answer with conditions [1].',summary:'Short SSPR guidance.',sources:[],form_links:links})});
  f.render();await send(f,'What is an SSPR?');
  const answer=f.values[1].at(-1);assert.equal(answer.text,'Short SSPR guidance.');
  assert.equal(answer.detailText,'Long answer with conditions [1].');assert.equal(answer.formLinks[0].url,links[0].url);
  assert.equal(chatHelpers().recentHistory(f.values[1]).at(-1).content,'Long answer with conditions [1].');
});

test('a simpler version retains the sources from the exact previous answer',async()=>{
  const source={citation_id:1,policy:'Reviewed policy',page:'1',section:'',source_url:null,evidence:[]};
  const f=chatFixture({ask:async()=>({answer:'Simpler explanation [1].',original_answer:'Full earlier answer [1].',sources:[],inherit_sources:true})});
  f.render();f.values[1]=[{sender:'bot',text:'Full earlier answer [1].',sources:[source]}];
  await send(f,'Explain that in simpler terms');const answer=f.values[1].at(-1);
  assert.equal(answer.sources[0].policy,'Reviewed policy');assert.equal(answer.detailText,'Full earlier answer [1].');
});

test('a clarification with no sources cannot inherit citations from an older answer',async()=>{
  const f=chatFixture({ask:async()=>({answer:'Simpler question.',sources:[],inherit_sources:true})});f.render();
  f.values[1]=[{sender:'bot',text:'Earlier policy',sources:[{citation_id:1,policy:'Earlier'}]},{sender:'bot',text:'Which funding?'}];
  await send(f,'Explain that');assert.equal(f.values[1].at(-1).sources.length,0);
});
