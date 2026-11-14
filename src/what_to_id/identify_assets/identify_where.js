// Identify's Where panel: the live map, loaded bare (map.html?embed=1&bare=1) the first time Where opens, with the area tools
// the map has (Draw area, Load GeoJSON, Find parks). The map holds the same filters through the address and wtid-selection;
// the area it draws or picks comes back as wtid-area. Expand map grows it to the whole window with a Show N cards button to
// return; Esc returns too.
// IdentifyWhere(o), o {box (#wbox: the foot with the Expand button), url (the map page), key() (the selection as text),
// set(area, hash, label) (the area changed), done() (back to the cards), leave() (Esc in the map's frame
// with it small: close the panel)}. Returns {show(), reset(), sync(), live()}.
var IdentifyWhere=(function(){
'use strict';
return function(o){
  var f=null,ok=false,btn=o.box.querySelector('#wexp'),count=document.querySelector('.sdone .n'),big=false;
  function text(){btn.textContent=big?'Show '+(count?count.textContent:'0')+' cards':'Expand map';}
  function grow(on){
    big=on;o.box.classList.toggle('big',on);btn.setAttribute('aria-expanded',String(on));text();
    if(!on)btn.focus();
  }
  btn.onclick=function(){if(big){grow(false);o.done();}else grow(true);};
  if(count)new MutationObserver(text).observe(count,{childList:true,characterData:true,subtree:true});
  // before the page's own Esc (the bar's panel, a dialog) so the first one only shrinks the map
  document.addEventListener('keydown',function(e){
    if(e.key==='Escape'&&big){e.preventDefault();e.stopPropagation();grow(false);}
  },true);
  function sync(){if(ok)f.contentWindow.postMessage({type:'wtid-selection',sel:o.key()},location.origin);}
  addEventListener('message',function(e){
    var d=e.data;
    if(!f||e.source!==f.contentWindow||e.origin!==location.origin||!d)return;
    if(d.type==='wtid-area'&&typeof d.area==='string'&&typeof d.hash==='string')o.set(d.area,d.hash,String(d.label||''));
    else if(d.type==='wtid-bare'&&d.esc){if(big)grow(false);else o.leave();}
  });
  return {
    show:function(){
      if(f)return;
      var u=new URL(o.url);u.search='?embed=1&bare=1';u.hash=location.hash.slice(1);
      f=document.createElement('iframe');f.title='Map';f.allow='geolocation';f.src=u.href;
      f.addEventListener('load',function(){ok=true;sync();});
      o.box.insertBefore(f,o.box.firstChild);
    },
    reset:function(){if(f){f.remove();f=null;ok=false;}this.show();},  // reload the map from the address, for a suggested area
    sync:sync,
    live:function(){return ok;}
  };
};
})();
