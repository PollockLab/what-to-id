// Start here: up to six finishable sets in one scrolling row between the search bar and the mode tabs. A mission is one group's cards in one 25 km
// blitz-gap cell of the current mode, sized for one "Identify these N on iNaturalist" batch. A click applies it as ordinary hash filters (identify_app.js).
// IdentifyMissions.pick(r, o) is the pure choice. r holds parallel arrays over the records in play: n, idx (the record), g (group), cell (-1 none),
// sp (what the per-species cut counts), score (the Prioritize score under the Blitz the gap weights), risk (1 at risk). o {min, max, top, cap}: a part keeps the
// cap best cards of each species (all when it holds one species), as the grid will show it, and counts when that is min..max cards. A part scores the sum of its cards'
// scores. The best part of a group not yet picked goes first, a group repeats only once every group has one. Returns [{g, cell, n, score, risk, rows}]
// best first, rows the record indexes of its cards best first.
// IdentifyMissions(o) draws the strip, o {box, names(g), mode(), lit(), records(), cap(), days(i), obs(ids) -> Promise of observations, embedded}; its
// update() redraws when the selection changed, hide() hides it, onpick(m) is called with the mission a card names (m.first: a record of its cell).
var IdentifyMissions=(function(){
'use strict';
var MIN=10,MAX=200,TOP=6,SHOWN=30;
function el(tag,cls,text){var e=document.createElement(tag);if(cls)e.className=cls;if(text!=null)e.textContent=text;return e;}
function pick(r,o){
  o=o||{};
  var lo=o.min||MIN,hi=o.max||MAX,top=o.top||TOP,cap=o.cap||Infinity,parts=new Map(),i,p,k;
  for(i=0;i<r.n;i++){
    if(r.cell[i]<0)continue;
    k=r.g[i]+'.'+r.cell[i];p=parts.get(k);
    if(!p){p={g:r.g[i],cell:r.cell[i],first:r.idx[i],n:0,score:0,risk:0,rows:[],all:[]};parts.set(k,p);}
    p.all.push(i);
  }
  var all=[];
  parts.forEach(function(v){
    var by=new Map();
    v.all.forEach(function(i){var l=by.get(r.sp[i]);if(!l)by.set(r.sp[i],l=[]);l.push(i);});
    by.forEach(function(l){
      l.sort(function(a,b){return r.score[b]-r.score[a]||r.idx[a]-r.idx[b];});
      (by.size===1?l:l.slice(0,cap)).forEach(function(i){v.rows.push(i);});});
    v.n=v.rows.length;delete v.all;
    if(v.n<lo||v.n>hi)return;
    v.rows.sort(function(a,b){return r.score[b]-r.score[a]||r.idx[a]-r.idx[b];});
    v.rows.forEach(function(i){v.score+=r.score[i];v.risk+=r.risk[i]?1:0;});
    v.rows=v.rows.map(function(i){return r.idx[i];});all.push(v);
  });
  all.sort(function(a,b){return b.score-a.score||b.n-a.n||a.g-b.g||a.cell-b.cell;});
  var out=[],used=new Set();
  while(out.length<top&&all.length){
    var j=0;
    while(j<all.length&&used.has(all[j].g))j++;
    if(j===all.length){used.clear();j=0;}  // every group has one: they repeat
    used.add(all[j].g);out.push(all.splice(j,1)[0]);
  }
  return out;
}
// the commonest place among the observations, and the first photo
function describe(obs){
  var c=new Map(),best='',photo='';
  obs.forEach(function(o){
    if(!o)return;
    if(!photo&&o.photos&&o.photos[0])photo=String(o.photos[0].url).replace('/square.','/medium.');
    if(o.place_guess)c.set(o.place_guess,(c.get(o.place_guess)||0)+1);});
  c.forEach(function(n,p){if(n>(c.get(best)||0))best=p;});
  return {place:best,photo:photo};
}
function make(o){
  var box=o.box,sig=null,T=0,seq=0,ul=el('ul','mrow');
  ul.setAttribute('role','list');box.hidden=true;box.append(el('h2','mlbl','Start here'),ul);
  function card(m){
    var li=el('li'),b=el('button','mcard'),ph=el('span','mph'),t=el('span','mtitle',o.names(m.g)),meta=el('span','mmeta');
    b.type='button';b.dataset.n=m.n;b.dataset.g=m.g;
    meta.textContent=m.n+' cards · '+o.mode()+' · gap '+o.days(m.first)+'/'+o.lit()+(m.risk?' · at risk':'');
    b.append(ph,t,meta);b.onclick=function(){o.onpick(m);};
    li.appendChild(b);m.t=t;m.ph=ph;return li;
  }
  function fill(m,n){
    o.obs(m.rows.slice(0,SHOWN)).then(function(obs){
      if(n!==seq)return;
      var d=describe(obs);
      if(d.place){m.title=o.names(m.g)+' · '+d.place;m.t.textContent=m.title;}
      if(d.photo){var img=el('img');img.alt='';img.loading='lazy';img.src=d.photo;m.ph.appendChild(img);}
    }).catch(function(){});
  }
  return {
    update:function(key){
      if(o.embedded)return;
      clearTimeout(T);
      T=setTimeout(function(){
        if(key===sig)return;sig=key;
        var ms=pick(o.records(),{cap:o.cap()});
        ul.textContent='';seq++;
        ms.forEach(function(m){m.title=o.names(m.g);ul.appendChild(card(m));});
        box.hidden=!ms.length;
        ms.forEach(function(m){fill(m,seq);});
      },60);
    },
    hide:function(){clearTimeout(T);box.hidden=true;sig=null;}
  };
}
make.pick=pick;
return make;
})();
