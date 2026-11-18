// One filter state for every view. The keys below are the filters (What, When, Where, Who, At risk, Introduced)
// and Identify's tab and Best x% cut, in the hash every page reads. Every link to another page of the site
// carries them, its own tokens (an id, a pick) first; a view that cannot apply one keeps it in its hash
// (held) and names it in a note, so it survives the round trip. A page whose hash is an anchor (How it
// works) has none of its own: it passes on the last ones seen in this tab. Inside Explore a pane posts its
// filters to the page, which holds the address.
var WtidCarry=window.WtidCarry||(function(){
var KEYS=['by','from','to','months','groups','only','acc','taxa','user','umode','umin','area','park','bcpark',
  'projects','risk','inv','lvl','kind','conf','gap','pri','base','rg','look'],
  NAME={groups:'What',taxa:'What',only:'What',acc:'What',by:'When',from:'When',to:'When',months:'When',
    user:'Who',umode:'Who',umin:'Who',area:'Where',park:'Where',bcpark:'Where',projects:'Where',risk:'At risk',
    inv:'Introduced',lvl:'Identify tab',kind:'Identify tab',conf:'Best x%',gap:'Survey gaps',pri:'Order',
    base:'Order',rg:'Unconfirmed',look:'Look-alikes'},
  // Clear filters drops these; Identify's tab and its order stay
  CLEAR=KEYS.filter(function(k){return ['lvl','kind','pri','base','gap','look'].indexOf(k)<0;}),BTN=[],
  SS='wtid-filters',anchors=!!document.querySelector('[data-anchors]'),OWN=null,sent=null,T=0;
function key(t){return t.split('=')[0];}
function take(h){return String(h||'').replace(/^#/,'').split('&').filter(function(t){
  return t.indexOf('=')>0&&KEYS.indexOf(key(t))>=0;});}
function now(){if(!anchors)return take(location.hash);try{return take(sessionStorage.getItem(SS));}catch(e){return [];}}
// the filters in the hash a view does not apply (own: the keys it does)
function held(own){return take(location.hash).filter(function(t){return own.indexOf(key(t))<0;});}
function link(a,f){
  var h=a.getAttribute('href');if(!h||h.charAt(0)==='#'||a.hasAttribute('download'))return;
  if(h!==a.dataset.done){var u;try{u=new URL(h,location.href);}catch(e){return;}
    if(u.origin!==location.origin||!/\.html$/.test(u.pathname))return;
    a.dataset.to=h.split('#')[0];a.dataset.own=u.hash.slice(1).split('&').filter(Boolean).join('&');}
  var own=a.dataset.own?a.dataset.own.split('&'):[],ks=own.map(key);
  if(own.some(function(t){return t.indexOf('=')<0;}))return;  // an anchor (terms.html#study) stays one
  var t=own.concat(f.filter(function(x){return ks.indexOf(key(x))<0;}));
  a.dataset.done=a.dataset.to+(t.length?'#'+t.join('&'):'');a.setAttribute('href',a.dataset.done);}
function note(f){
  var s=document.querySelector('.site-shell,.appbar');if(!s||!OWN)return;
  var n=document.getElementById('site-held'),own=typeof OWN==='function'?OWN():OWN,
    l=f.filter(function(t){return own.indexOf(key(t))<0;}).map(function(t){return NAME[key(t)];});
  l=l.filter(function(x,i){return l.indexOf(x)===i;});
  if(!n){n=document.createElement('p');n.id='site-held';n.className='site-held';n.setAttribute('role','status');s.after(n);}
  n.hidden=!l.length;n.textContent=l.length?'Kept for the other views, not applied here: '+l.join(', ')+'.':'';}
function sweep(){
  T=0;var f=now();
  if(!anchors)try{sessionStorage.setItem(SS,f.join('&'));}catch(e){}
  document.querySelectorAll('a[href]').forEach(function(a){link(a,f);});
  if(parent!==window&&f.join('&')!==sent){sent=f.join('&');parent.postMessage({type:'wtid-carry',tokens:f},location.origin);}
  var d=f.some(function(t){return CLEAR.indexOf(key(t))>=0;});BTN.forEach(function(b){b.hidden=!d;});
  note(f);}
function soon(){if(!T)T=setTimeout(sweep,30);}
// every write of the address, by any view, and every link drawn later
['replaceState','pushState'].forEach(function(m){var o=history[m];
  history[m]=function(){var r=o.apply(this,arguments);soon();return r;};});
addEventListener('hashchange',soon);
['pointerdown','focusin','click','contextmenu'].forEach(function(e){document.addEventListener(e,function(ev){
  var a=ev.target.closest&&ev.target.closest('a[href]');if(a)link(a,now());},true);});
function start(){sweep();new MutationObserver(soon).observe(document.body,{childList:true,subtree:true});}
if(document.body)start();else addEventListener('DOMContentLoaded',start);
return {KEYS:KEYS,NAME:NAME,take:take,held:held,sweep:sweep,link:function(a){link(a,now());},
  // a view that does not apply every filter names the keys it does (or a function of them), for the note
  own:function(o){OWN=o;soon();},
  // a Clear filters button: shown while a filter is set; a click hands go() the address without them
  clear:function(b,go){BTN.push(b);soon();b.addEventListener('click',function(){
    go(location.hash.slice(1).split('&').filter(function(t){return t&&CLEAR.indexOf(key(t))<0;}));});}};
})();
