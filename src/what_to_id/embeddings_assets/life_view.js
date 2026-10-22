// The photo space drawn as a map of life (life_map.js draws it): Clades / Look-alikes, the hover text and the
// hash tokens life=look and clade=. The map of all life is always drawn; over it, the clade that fills the view
// gets a sharper map of its own, transparent outside the clade, so zooming is the way in and back out. A click
// on a region flies to it. The map draws every placed record; the app draws the points the filters keep over it.
function LifeView(o){
'use strict';
var S=o.S,$=o.$,LM=LifeMap,nf=new Intl.NumberFormat('en-CA'),cache=new Map(),life=null,M=null,look,lookP=null,run=0,
  tm=0,pin=-1,pinB=null;
var h0=new URLSearchParams(location.hash.slice(1)),mode=h0.get('life')==='look'?'look':'life',
  want=+h0.get('clade')||0,row=-1,A=null,byId=null,placed=null;
var MIN_PX=11,FLY=600;  // a label drawn smaller than MIN_PX does not read, so it is left out
// Deep in, a zoom's cells draw as blocks: its map fades out as a cell grows from FADE[0] to FADE[1] screen px,
// and the points over the life map carry the picture.
var FADE=[6,12];
// Zoom grid cells on the long side, from the screen at load (a resize keeps it, so the cache stays valid):
// about one cell a device pixel, in steps of 256, at most 1024 (a 3M-record zoom builds in about 1 s there).
var ZOOM_LONG=Math.max(512,Math.min(1024,256*Math.ceil(Math.max(innerWidth,innerHeight)*(devicePixelRatio||1)/256)));
function on(){return !!life;}
function name(r){var t=S.TAXA[r];return t[0]+(t[1]?' ('+t[1]+')':'');}
function press(id,v){$(id).setAttribute('aria-pressed',v?'true':'false');}
function bar(){
  press('vclade',mode==='life');press('vlook',mode==='look');
  $('vlook').disabled=look===null;
  $('vlook').title=look===null?'This map has no look-alike file yet':'';
  $('lwhere').textContent=row>=0?name(row):'All life';
  $('lonly').hidden=row<0;
  if(row>=0)$('lonly').title='Keep only the records of '+S.TAXA[row][0];
  $('lnote').textContent=look===null?'No look-alike file for this map.':'';
  var lg=$('llegend');lg.hidden=mode!=='look';
  if(mode==='look'&&!lg.childNodes.length){LM.LEVELS.slice(0,4).forEach(function(t,v){
    var i=document.createElement('i'),c=LM.RAMP[Math.round(v/3*(LM.RAMP.length-1))];
    i.style.background='rgb('+c.join(',')+')';lg.appendChild(i);lg.appendChild(document.createTextNode(t+(v===3?' or further':'')));});
    lg.appendChild(document.createTextNode('. Skips pairs often photographed together (GloBI).'));}
}
// pool-lookalike.bin sits beside the shards and carries their cache key; null when it is not there.
function lookFile(){
  if(lookP)return lookP;
  var sh=S.META.shards,q=String(sh[0].file).split('?')[1],n=sh.reduce(function(t,s){return t+s.n;},0);
  lookP=fetch(new URL('pool-lookalike.bin'+(q?'?'+q:''),o.MAP)).then(function(r){
    if(!r.ok)throw new Error(r.status);return r.arrayBuffer();})
    .then(EmbeddingsLayout.gunzip).then(function(b){return LM.decodeLookalike(b,n);})
    .catch(function(e){console.warn('No look-alike levels:',e.message);return null;});
  return lookP;
}
function canvas(m,px){
  var c=document.createElement('canvas');c.width=m.W;c.height=m.H;
  c.getContext('2d').putImageData(new ImageData(px,m.W,m.H),0,0);return c;
}
// The map in greys, so the points a filter keeps are the only colour over it.
function grey(m,k){
  if(!m[k+'G']){var a=new Uint8ClampedArray(k==='look'?m.look:m.image);
    for(var i=0;i<a.length;i+=4)a[i]=a[i+1]=a[i+2]=.3*a[i]+.59*a[i+1]+.11*a[i+2];
    m[k+'G']=canvas(m,a);}
  return m[k+'G'];
}
function opts(r){
  var P=S.P;
  return {pos:P.pos,n:P.n,tax:P.tax,grp:P.grp,groups:S.META.groups.length,color:o.color,T:S.TAXA,ranks:S.META.ranks,
    A:A,clade:r,src:P.src};
}
// A clade's colour as a region of a map already drawn, or null.
function rgbOf(r){
  var ms=[life].concat(Array.from(cache.values()));
  for(var i=0;i<ms.length;i++)for(var s=0;ms[i]&&s<ms[i].slots.length;s++)if(ms[i].slots[s].row===r)return ms[i].slots[s].rgb;
  return null;
}
function make(r){
  var k=S.META.ranks,c=r>=0?A['class'][r]:-1;
  // an order's families take their hues from the order's colour on its class's map, so that map comes first
  if(LM.rankOf(S.TAXA,k,r)==='order'&&c>=0&&!rgbOf(r)&&!cache.has(c))make(c);
  var t0=performance.now(),m=LM.build(Object.assign(opts(r),{look:look,long:r<0?512:ZOOM_LONG,rgb:rgbOf(r),known:rgbOf}));
  console.info('map of '+(r<0?'life':S.TAXA[r][0])+' built in '+Math.round(performance.now()-t0)+' ms');
  if(m){if(m.look)m.lookC=canvas(m,m.look);m.imgC=canvas(m,m.image);}
  if(r<0)life=m;else{if(cache.size>8)cache.clear();cache.set(r,m);}
  return m;
}
// The layout box the plot shows.
function view(){
  var b=$('plot'),k=Math.pow(2,S.vs.zoom),w=b.clientWidth/2/k,h=b.clientHeight/2/k,t=S.vs.target;
  return [t[0]-w,t[1]-h,t[0]+w,t[1]+h];
}
// The clade the view looks at, its map drawn on first use; a new map may show a deeper clade still. A clade flown
// to holds until the view moves, though its box may hold more of its parent than of it.
function refocus(){
  if(!life)return;
  if(!(S.framed&&S.framed.b===pinB&&S.vs===S.framed.vs))pin=-1;
  var r=pin>=0?pin:LM.focus(life,chain(),A,S.TAXA,S.META.ranks,view());
  if(r===row)return;
  var me=++run;row=r;bar();o.writeHash();
  if(r<0||cache.has(r)){M=r<0?null:cache.get(r);o.redraw();return;}
  o.status('Drawing the map of '+S.TAXA[r][0]+'…');
  setTimeout(function(){
    if(me!==run)return;
    M=make(r);o.status('');o.redraw();refocus();  // too few records: M is null and the life map stays alone
  },20);
}
// The focused map and its ancestors' maps still cached, shallow to deep.
function chain(){
  return M?Array.from(cache.values()).filter(function(m){return m&&A[m.rank][M.clade]===m.clade;})
    .sort(function(a,b){return LM.RANKS.indexOf(a.rank)-LM.RANKS.indexOf(b.rank);}):null;
}
function moved(){clearTimeout(tm);tm=setTimeout(refocus,200);}
function set(m){
  if(m==='look'&&look===null)return;
  mode=m;bar();o.writeHash();o.redraw();
}
// with room around the land for the kingdom labels
function padded(e){var p=.1*Math.max(e[2]-e[0],e[3]-e[1]);return [e[0]-p,e[1]-p,e[2]+p,e[3]+p];}
// Back to all life, framed as on load; false when there is no map to go back to.
function home(){if(!on())return false;o.frame(padded(life.ext));return true;}
// Flies the view to clade r's territory, where the view's focus then finds it.
function fly(r,ms){var b=LM.extent(opts(r));if(b){pin=r;pinB=b;o.frame(b,ms);}}
$('vclade').addEventListener('click',function(){set('life');});
$('vlook').addEventListener('click',function(){set('look');});
$('lonly').addEventListener('click',function(){if(row>=0)o.only(S.TAXA[row][2]);});

function text(t){
  if(!on())return null;
  if(t.layer&&t.layer.id.indexOf('life-lbl')===0&&t.object)return name(t.object.row);
  var u=t.coordinate&&LM.region(life,M,t.coordinate[0],t.coordinate[1]);
  if(!u)return '';
  var m=u.map,sl=m.slots[u.hit.slot],out=[],fine=m.fine;
  if(sl.row>=0){
    out.push(name(sl.row),nf.format(sl.n)+' records');
    if(sl.agree!=null)out.push(Math.round(100*sl.agree)+'% of its photo neighbours are also '+S.TAXA[sl.row][0]);
  }else out.push('Other '+(fine==='class'?'classes':fine==='family'?'families':'orders'),nf.format(sl.n)+' records');
  var lev=u.hit.levels;
  if(mode==='look'&&lev){
    var tot=lev.reduce(function(a,b){return a+b;},0);
    if(tot)out.push('Closest look-alike here:');
    lev.forEach(function(v,i){if(tot&&v/tot>=.01)out.push('  '+Math.round(100*v/tot)+'% '+LM.LEVELS[i]);});
  }
  return out.join('\n');
}
// A click the points did not take: a label or a region flies the view to its clade.
function click(t){
  if(!on())return false;
  var r=-1;
  if(t.layer&&t.layer.id.indexOf('life-lbl')===0&&t.object)r=t.object.row;
  else{var u=t.coordinate&&LM.region(life,M,t.coordinate[0],t.coordinate[1]);if(u)r=u.row;}
  if(r>=0)fly(r,FLY);
  return true;
}
// The life map, the focused clade's map, then pts (the app's points layer), then the labels that read at the
// view's zoom; the maps dim while points are drawn over them, and turn grey while a filter holds some back;
// labels whose clade has no kept point fade then (own layers, as a text layer's outline colour is one value for
// the layer).
var fk=null,fh=null;
// Per taxon row, whether its clade holds a kept point (grp: the picked groups); rebuilt per filter change.
function holds(grp){
  var key=S.PDV+':'+grp;
  if(fk!==key){
    var P=S.P,ok=new Set(grp),seen=new Uint8Array(S.TAXA.length),ks=Object.keys(A);fh=new Uint8Array(S.TAXA.length);
    for(var i=0;i<P.n;i++){var r=P.tax[i];
      if(r>=0&&!seen[r]&&S.keep[i]&&ok.has(P.grp[i])){seen[r]=fh[r]=1;ks.forEach(function(k){if(A[k][r]>=0)fh[A[k][r]]=1;});}}
    fk=key;
  }
  return fh;
}
// The labels to place: the focused map's, and the life map's for the clades beside the focus (those inside it or
// above it would repeat or cover its own).
function candidates(){
  if(!M)return life.labels;
  var T=S.TAXA,k=S.META.ranks,fr=LM.rankOf(T,k,row);
  return life.labels.filter(function(d){return A[fr][d.row]!==row&&A[LM.rankOf(T,k,d.row)][row]!==d.row;})
    .concat(M.labels);
}
function layers(pts,dim,filt,grp){
  var z=Math.round(S.vs.zoom*4)/4;
  if(!placed||placed.z!==z||placed.M!==M)placed={z:z,M:M,L:LM.place(candidates(),z,MIN_PX)};
  var h=filt?holds(grp):null;
  function lbl(id,data,weight,f){
    return new deck.TextLayer({id:id,data:data,getPosition:function(d){return d.pos;},getText:function(d){return d.text;},
      getSize:function(d){return d.size;},sizeUnits:'common',sizeMaxPixels:weight==='800'?22:30,
      fontFamily:'system-ui,-apple-system,"Segoe UI",sans-serif',fontWeight:weight,characterSet:'auto',
      getColor:[29,29,27,f?55:235],fontSettings:{sdf:true},outlineWidth:3,outlineColor:[255,255,255,f?55:220],pickable:true});
  }
  function lbls(id,data,weight){
    return h?[lbl(id+'-f',data.filter(function(d){return !h[d.row];}),weight,1),
      lbl(id,data.filter(function(d){return h[d.row];}),weight)]:[lbl(id,data,weight)];
  }
  var k=mode==='look'&&life.lookC?'look':'img';
  function map(id,m){var f=m===life?1:Math.min(1,Math.max(0,(FADE[1]-m.cs*Math.pow(2,z))/(FADE[1]-FADE[0])));
    return new deck.BitmapLayer({id:id,image:filt?grey(m,k):m[k+'C'],bounds:m.ext.slice(),opacity:(dim?.4:1)*f});}
  var L=placed.L,out=[map('life-img',life)];
  if(M)out.push(map('life-zoom',M));
  return out.concat([pts],
    lbls('life-lbl',L.filter(function(d){return !d.italic&&!d.bold;}),'600'),
    lbls('life-lbl-i',L.filter(function(d){return d.italic;}),'italic 500'),
    lbls('life-lbl-k',L.filter(function(d){return d.bold;}),'800'));
}
// The view's tokens replace any already in the hash list h.
function hash(h){
  h=h.filter(function(t){var k=t.split('=')[0];return k!=='life'&&k!=='clade';});
  if(mode==='look')h.push('life=look');
  if(row>=0||want)h.push('clade='+(row>=0?S.TAXA[row][2]:want));  // a clade still waiting for the join stays
  return h;
}
// The join brings the names and the rows the map needs, and the map is drawn then; a clade in the address is
// where the view starts, and a subset or an opened record keeps its own view.
function joined(){
  if(!S.TAXA||!S.META)return;
  A=LM.ancestors(S.TAXA,S.META.ranks);byId=new Map();
  S.TAXA.forEach(function(t,i){byId.set(t[2],i);});
  cache.clear();fk=null;life=M=null;row=-1;placed=null;$('lifebar').hidden=false;
  var r=want&&byId.has(want)?byId.get(want):-1,me=++run;
  if(r>=0&&!LM.canZoom(S.TAXA,S.META.ranks,r))r=-1;
  o.status('Drawing the map of life…');
  lookFile().then(function(L){
    look=L;if(L===null&&mode==='look'){mode='life';o.writeHash();}
    setTimeout(function(){
      if(me!==run)return;
      make(-1);o.status('');want=0;bar();o.writeHash();
      if(!life){o.redraw();return;}  // too few records: points alone
      if(!S.subset&&S.sel<0){if(r>=0)fly(r);else home();}
      o.redraw();refocus();
    },20);
  });
}
return {on:on,layers:layers,text:text,click:click,hash:hash,joined:joined,home:home,moved:moved};
}
