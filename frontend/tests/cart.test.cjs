const assert = require('node:assert/strict');
const {readFileSync} = require('node:fs');
const {join} = require('node:path');
const {test} = require('node:test');
const vm = require('node:vm');
const ts = require('typescript');
const {parseHTML} = require('linkedom');

function fixture(transform = text => text, location = {hostname:'solutions.sciquest.com',pathname:'/apps/Router/SimpleCart'}) {
  const html = transform(readFileSync(join(__dirname,'fixtures/cruzbuy-cart.html'),'utf8'));
  const {document} = parseHTML(html);
  const code = ts.transpileModule(readFileSync(join(__dirname,'../services/cart.ts'),'utf8'),{
    compilerOptions:{module:ts.ModuleKind.CommonJS,target:ts.ScriptTarget.ES2022},
  }).outputText;
  const module={exports:{}};
  vm.runInNewContext(code,{module,exports:module.exports,document,location,
    require:() => ({browser:{}})});
  return module.exports.readCruzBuyCart;
}

test('observed cart layout extracts item and tax but does not invent absent charges', () => {
  const cart=fixture()();
  assert.equal(cart.items.length,1);
  assert.equal(cart.items[0].description,'DEMO DEAD BLOW HAMMER');
  assert.equal(cart.items[0].supplier,'Demo Tools Supplier');
  assert.equal(cart.items[0].quantity,'1');
  assert.equal(cart.subtotal,'33.24');
  assert.equal(cart.tax,'3.24');
  assert.equal(cart.total,'36.48');
  assert.equal(cart.shipping,null);
  assert.equal(cart.handling,null);
  assert.deepEqual(Object.keys(cart).sort(),['currency','handling','items','shipping','subtotal','tax','total']);
});

test('cart reader rejects unrelated hosts and pages', () => {
  assert.throws(fixture(x=>x,{hostname:'mail.google.com',pathname:'/apps/Router/SimpleCart'}),/Open the CruzBuy/);
  assert.throws(fixture(x=>x,{hostname:'solutions.sciquest.com',pathname:'/apps/Router/OtherPage'}),/Open the CruzBuy/);
});

test('changed selectors fail rather than silently omit cart lines', () => {
  assert.throws(fixture(x=>x.replace('LineItemSixPackdemo1','DifferentLayout')),/No supported cart item/);
  assert.throws(fixture(x=>x.replace('ProductDescription','ChangedDescription')),/description, supplier, or quantity/);
});

test('non-USD currencies and malformed amounts fail closed', () => {
  assert.throws(fixture(x=>x.replace('value="USD"','value="EUR"')),/supports USD/);
  assert.throws(fixture(x=>x.replace('>33.24</div>','>not a price</div>')),/could not be read safely/);
});

test('explicit shipping and handling rows are read', () => {
  const cart=fixture(x=>x.replace('<p>Shipping', '<table><tr><td>Shipping</td><td>5.00</td></tr><tr><td>Handling</td><td>0.00</td></tr></table><p>Shipping'))();
  assert.equal(cart.shipping,'5.00');
  assert.equal(cart.handling,'0.00');
});

function pageFixture() {
  const values=[],effects=[],refs=[];
  let cursor=0,refCursor=0,effectCursor=0;
  let auth={userProfile:{uid:'a',clearance:'none'},isApproved:true,isLoading:false,refreshSession:async()=>{}};
  let resolve;
  const pending=new Promise(r=>{resolve=r;});
  const react={
    createElement:(type,props,...children)=>({type,props:{...props,children}}),
    useState:(initial)=>{const i=cursor++;if(!(i in values))values[i]=initial;return[values[i],v=>{values[i]=typeof v==='function'?v(values[i]):v;}];},
    useRef:(initial)=>{const i=refCursor++;return refs[i]??(refs[i]={current:initial});},
    useEffect:(callback,deps)=>{const i=effectCursor++;if(!effects[i]||deps.some((d,n)=>d!==effects[i][n])){effects[i]=deps;callback();}},
  };
  const code=ts.transpileModule(readFileSync(join(__dirname,'../components/pages/CartPage.tsx'),'utf8'),{
    compilerOptions:{module:ts.ModuleKind.CommonJS,target:ts.ScriptTarget.ES2022,jsx:ts.JsxEmit.React,esModuleInterop:true},
  }).outputText;
  const module={exports:{}};
  vm.runInNewContext(code,{module,exports:module.exports,require:name=>{
    if(name==='react')return react;
    if(name==='react-router-dom')return{Link:()=>null};
    if(name.endsWith('AuthContext'))return{useAuth:()=>auth};
    if(name.endsWith('services/cart'))return{captureCart:()=>pending,requestCartGuide:()=>pending};
    if(name.endsWith('services/agent'))return{citationUrl:()=>undefined};
    if(name.endsWith('services/auth'))return{SessionError:Error};
    throw Error(name);
  }});
  return{values,resolve,render:()=>{cursor=0;refCursor=0;effectCursor=0;return module.exports.default();},
    changeSession:changes=>{auth={...auth,...changes};}};
}
function find(tree,type) {
  if(!tree||typeof tree!=='object')return;
  if(tree.type===type)return tree;
  for(const child of (tree.props?.children??[]).flat(Infinity)){
    const match=find(child,type);if(match)return match;
  }
}

test('pending cart extraction cannot restore purchase data after sign-out', async()=>{
  const f=pageFixture();f.render();
  const pending=find(f.render(),'button').props.onClick();
  f.changeSession({userProfile:null,isApproved:false});f.render();
  f.resolve(fixture()());await pending;
  assert.equal(f.values[0],null);
  assert.equal(f.values[5],null);
});

test('pending guidance cannot expose the previous account cart after account switch', async()=>{
  const f=pageFixture();f.render();f.values[0]=fixture()();f.values[2]=true;f.values[3]=true;
  const pending=find(f.render(),'form').props.onSubmit({preventDefault(){}});
  f.changeSession({userProfile:{uid:'b',clearance:'none'}});f.render();
  f.resolve({answer:'Previous account response',sources:[],forms:[]});await pending;
  assert.equal(f.values[0],null);
  assert.equal(f.values[5],null);
});
