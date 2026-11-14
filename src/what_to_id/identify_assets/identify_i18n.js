// Language and names for the Identify page: one EN / FR switch for all its text and the species' common names, and a names
// setting (Latin, Common, Both), both kept in localStorage. A change reloads the page, so every number, date and name is drawn afresh.
// The modules keep writing English. In French a MutationObserver puts identify_fr.js (I18N_FR: words by their English text, and
// rules for the lines with numbers or names in them) over each text node and attribute as it appears; code that reads a line back
// uses raw(). Names never change order: nothing here touches which records, or in what order, the page serves.
// I18N: {lang, loc, names, nf, tr(s), raw(el), api(url), taxa(rows, fr), nm(latin), set(key, value), settings(ctx)}.
var I18N=(function(){
'use strict';
var LK='wtid-lang',NK='wtid-names',ATTR=['aria-label','title','placeholder','alt','data-k'],SKIP=/^(SCRIPT|STYLE|TEXTAREA)$/,
  D=typeof I18N_FR==='undefined'?{words:{},rules:[]}:I18N_FR,ORIG=new WeakMap(),CM=new Map(),own=Object.prototype.hasOwnProperty;
function get(k){try{return localStorage.getItem(k);}catch(e){return null;}}
function put(k,v){try{localStorage.setItem(k,v);}catch(e){}}
var lang=get(LK),names=get(NK);
if(lang!=='en'&&lang!=='fr')lang=/^fr/i.test(navigator.language||'')?'fr':'en';
if(names!=='latin'&&names!=='common')names='both';
var loc=lang==='fr'?'fr-CA':'en-CA';
document.documentElement.lang=lang;
// the French of one trimmed line: its own entry, else the first rule that fits
function fix(s){return s.replace(/(\d) ?%/g,'$1 %').replace(/(\d) (?=\d{3}(?!\d))/g,'$1 ');}  // French sets a space before % and in thousands
function one(k){
  if(own.call(D.words,k))return fix(D.words[k]);
  for(var j=0;j<D.rules.length;j++)if(D.rules[j][0].test(k))return fix(k.replace(D.rules[j][0],D.rules[j][1]));
  return k;
}
// blanks around a line stay and those inside it count as one; a line of " · " parts that has no entry as a whole is done part by part
function tr(s){
  var m=/^(\s*)([\s\S]*?)(\s*)$/.exec(s),k=m[2].replace(/\s+/g,' '),v;
  if(lang!=='fr'||!/[A-Za-z]/.test(k))return s;
  v=one(k);if(v===k&&k.indexOf(' · ')>0)v=k.split(' · ').map(one).join(' · ');
  return v===k?s:m[1]+v+m[3];
}
function text(n){
  var p=n.parentNode,o=ORIG.get(n),f;
  if(!p||SKIP.test(p.nodeName)||p.closest&&p.closest('i,.com,.cn')||o&&o.fr===n.data)return;
  f=tr(n.data);if(f!==n.data){ORIG.set(n,{en:n.data,fr:f});n.data=f;}
}
function walk(n){
  if(n.nodeType===3)return text(n);
  if(n.nodeType!==1||SKIP.test(n.nodeName))return;
  ATTR.forEach(function(a){if(n.hasAttribute(a))attr(n,a);});
  for(var c=n.firstChild;c;c=c.nextSibling)walk(c);
}
function attr(n,a){var v=n.getAttribute(a),f=tr(v);if(f!==v)n.setAttribute(a,f);}
if(lang==='fr'){
  new MutationObserver(function(ms){ms.forEach(function(m){
    if(m.type==='childList')m.addedNodes.forEach(walk);
    else if(m.type==='characterData')text(m.target);
    else attr(m.target,m.attributeName);});}).observe(document.documentElement,
    {childList:true,subtree:true,characterData:true,attributes:true,attributeFilter:ATTR});
  walk(document.documentElement);
}
// an element's text as the modules wrote it, English
function raw(e){
  var s='',w=document.createTreeWalker(e,4),n,o;
  while((n=w.nextNode())){o=ORIG.get(n);s+=o&&o.fr===n.data?o.en:n.data;}
  return s;
}
// iNaturalist's answers carry common names in this language
function api(u){return lang==='fr'?u+(u.indexOf('?')<0?'?':'&')+'locale=fr':u;}
// The taxa table's common names: the French one from `fr` {taxon id: name} when there is one (else the English stays, and with none the
// Latin shows); under Latin only the table holds none. CM answers a Latin name's common name for the lines that name a look-alike.
function taxa(rows,fr){
  rows.forEach(function(t){
    var f=lang==='fr'&&fr&&fr[t[2]];if(f)t[1]=f;
    CM.set(t[0],names==='latin'?'':t[1]);if(names==='latin')t[1]='';});
  return rows;
}
// a species' name as the setting shows it: italic Latin, or under Common its common name (the table's, else com) when it has one
function nm(la,com){
  var c=names==='common'&&(com||CM.get(la)),e=document.createElement(c?'span':'i');
  e.className=c?'cn':'';e.textContent=c||la;e.dataset.la=la;return e;
}
function set(k,v){put(k==='lang'?LK:NK,v);try{sessionStorage.setItem('wtid-set',k==='lang'?'lang':'1');}catch(e){}location.reload();}
return {lang:lang,loc:loc,names:names,nf:new Intl.NumberFormat(loc),tr:tr,raw:raw,api:api,taxa:taxa,nm:nm,set:set};
})();
