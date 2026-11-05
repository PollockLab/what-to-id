// The records a visitor bookmarked, in one localStorage list shared by the map and the photo space (same origin, so the
// split view's two frames see one list; the `storage` event carries a change from one frame to the other).
// SavedRecords {has(id), toggle(id), ids(), clear(), on(fn), controls(id)}; controls(id) is the card's Save button,
// "Saved (n)" Identify link and Clear button, kept current until the card is rebuilt.
var SavedRecords=(function(){
'use strict';
var KEY='wtid-saved',mem=[],fns=[];  // mem: the list when storage is blocked, so a page still saves for its lifetime
function read(){
  try{var a=JSON.parse(localStorage.getItem(KEY));if(Array.isArray(a))mem=a.filter(function(v){return Number.isSafeInteger(v)&&v>0;});}
  catch(e){}
  return mem;
}
function write(a){mem=a;try{localStorage.setItem(KEY,JSON.stringify(a));}catch(e){}fns.slice().forEach(function(f){f();});}
function el(tag,cls,text){var e=document.createElement(tag);if(cls)e.className=cls;if(text!=null)e.textContent=text;return e;}
var S={
  has:function(id){return read().indexOf(id)>=0;},
  ids:function(){return read().slice();},
  toggle:function(id){var a=read().slice(),k=a.indexOf(id);if(k>=0)a.splice(k,1);else a.push(id);write(a);return k<0;},
  clear:function(){write([]);},
  on:function(f){fns.push(f);},
  controls:function(id){
    var box=el('div','sv'),b=el('button'),a=el('a'),x=el('button',null,'Clear saved');
    b.type=x.type='button';a.target='_blank';a.rel='noopener';
    function sync(){
      var on=S.has(id),n=S.ids();
      b.textContent=on?'★ Saved':'☆ Save';b.setAttribute('aria-pressed',String(on));
      a.hidden=x.hidden=!n.length;a.textContent='Saved ('+n.length+')';
      // IdentifyLinks.batches opens the first 200 (newest first); a longer list needs the next batches by hand
      if(n.length)a.href=IdentifyLinks.batches(n)[0].url;
    }
    function live(){if(!box.isConnected){fns.splice(fns.indexOf(live),1);return;}sync();}  // gone once the card is rebuilt
    b.onclick=function(){S.toggle(id);};x.onclick=S.clear;
    box.append(b,a,x);sync();S.on(live);return box;
  }
};
addEventListener('storage',function(e){if(e.key===KEY||e.key===null)fns.slice().forEach(function(f){f();});});
return S;
})();
