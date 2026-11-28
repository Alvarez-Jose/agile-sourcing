const assert=require('node:assert/strict');
const {readFileSync}=require('node:fs');
const {join}=require('node:path');
const {test}=require('node:test');
const vm=require('node:vm');
const ts=require('typescript');

const url='https://financial.ucsc.edu/Financial_Affairs_Forms/Source_Selection_Justification_Form.pdf';
const links=[{title:'Source Selection & Price Reasonableness Justification Form (SSPR)',url,
  aliases:['Source Selection & Price Reasonableness Justification Form (SSPR)','SSPR form','SSPR']}];
function render(text, metadata=links) {
  const module={exports:{}};
  const code=ts.transpileModule(readFileSync(join(__dirname,'../components/ChatAnswerText.tsx'),'utf8'),{
    compilerOptions:{module:ts.ModuleKind.CommonJS,target:ts.ScriptTarget.ES2022,jsx:ts.JsxEmit.React,esModuleInterop:true},
  }).outputText;
  vm.runInNewContext(code,{module,exports:module.exports,URL,require:()=>({createElement:(type,props,...children)=>({type,props:{...props,children}})})});
  return module.exports.ChatAnswerText({text,links:metadata});
}
function nodes(tree,type) {
  if(!tree||typeof tree!=='object')return[];
  return [...(tree.type===type?[tree]:[]),...(tree.props?.children??[]).flat(Infinity).flatMap(child=>nodes(child,type))];
}

test('form mentions become official inline links with safe new-tab attributes',()=>{
  const anchors=nodes(render('Prepare the SSPR form and review SSPR guidance.'),'a');
  assert.equal(anchors.length,2);
  for(const a of anchors){assert.equal(a.props.href,url);assert.equal(a.props.target,'_blank');assert.equal(a.props.rel,'noopener noreferrer');}
});

test('model Markdown cannot replace the verified form URL',()=>{
  const anchors=nodes(render('[SSPR](https://evil.example/download)'),'a');
  assert.equal(anchors.length,1);assert.equal(anchors[0].props.href,url);
});

for(const value of ['javascript:alert(1)','http://financial.ucsc.edu/form','https://ucsc.edu.evil.example/form','https://user:pass@financial.ucsc.edu/form','https://evil.example/form']) {
  test(`unsafe or unverified destination remains plain text: ${value}`,()=>{
    assert.equal(nodes(render('SSPR',[{...links[0],url:value}]),'a').length,0);
  });
}

test('an FAQ mention is not mislabeled as a link to the SSPR form',()=>{
  assert.equal(nodes(render('See the SSPR FAQ, then use the SSPR form.'),'a').length,1);
  assert.equal(nodes(render('XSSPR is an unrelated name.'),'a').length,0);
});

test('HTML and unknown form links are never rendered as executable markup',()=>{
  const tree=render('<script>alert(1)</script> [Federal Funds Checklist](https://unknown.example/form)',[]);
  assert.equal(nodes(tree,'a').length,0);assert.equal(nodes(tree,'script').length,0);
});

test('full form title uses a single link rather than nested acronym links',()=>{
  assert.equal(nodes(render(links[0].title),'a').length,1);
});
