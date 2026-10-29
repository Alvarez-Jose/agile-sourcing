const assert = require('node:assert/strict');
const {readFileSync} = require('node:fs');
const {join} = require('node:path');
const {test} = require('node:test');
const vm = require('node:vm');
const ts = require('typescript');

function service() {
  const code = ts.transpileModule(readFileSync(join(__dirname,'../services/agent.ts'),'utf8'),{
    compilerOptions:{module:ts.ModuleKind.CommonJS,target:ts.ScriptTarget.ES2022},
  }).outputText;
  const module={exports:{}};
  vm.runInNewContext(code,{module,exports:module.exports,URL,AbortSignal,
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

function chatFixture() {
  const values=[],effects=[],refs=[];
  let cursor=0,refCursor=0,effectCursor=0;
  let auth={userProfile:{uid:'user-a',clearance:'internal'},isAuthenticated:true,isApproved:true,isLoading:false,refreshSession:async()=>{}};
  let resolve;
  const pending=new Promise(r=>{resolve=r;});
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
  vm.runInNewContext(code,{module,exports:module.exports,require:(name)=>{
    if(name==='react')return react;
    if(name.endsWith('AuthContext'))return{useAuth:()=>auth};
    if(name.endsWith('Login'))return{default:()=>null};
    if(name.endsWith('services/agent'))return{askQuestion:()=>pending,citationUrl:()=>undefined};
    if(name.endsWith('services/auth'))return{SessionError:Error};
    throw Error(name);
  }});
  return {values,resolve,render:()=>{cursor=0;refCursor=0;effectCursor=0;return module.exports.ChatPage();},
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
