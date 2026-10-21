// The photo space drawn as a map of life (life_map.js draws it): Clades / Look-alikes, zoom by click with Up back
// out, the hover text and the hash tokens life=look and clade=. The map draws every placed record; the app draws
// the points the filters keep over it.
function LifeView(o){
'use strict';
var S=o.S,$=o.$,LM=LifeMap,nf=new Intl.NumberFormat('en-CA'),cache=new Map(),M=null,look,lookP=null,run=0;
var h0=new URLSearchParams(location.hash.slice(1)),mode=h0.get('life')==='look'?'look':'life',
  want=+h0.get('clade')||0,row=-1,A=null,byId=null,placed=null;
var MIN_PX=11;  // a label drawn smaller than this does not read, so it is left out
function on(){return !!M;}
function name(r){var t=S.TAXA[r];return t[0]+(t[1]?' ('+t[1]+')':'');}
function press(id,v){$(id).setAttribute('aria-pressed',v?'true':'false');}
function bar(){
  press('vclade',mode==='life');press('vlook',mode==='look');
  $('vlook').disabled=look===null;
  $('vlook').title=look===null?'This map has no look-alike file yet':'';
  var up=row>=0?LM.parentOf(A,S.TAXA,S.META.ranks,row):-2;
  $('lup').hidden=up===-2;
  $('lup').textContent=up>=0?'Up to '+S.TAXA[up][0]:'Up to all life';
  $('lwhere').textContent=row>=0?name(row):'All life';
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
function draw(r,fit){
  var me=++run;row=r;bar();o.writeHash();
  if(cache.has(r)){show(cache.get(r),fit);return;}
  o.status('Drawing the map of life…');
  lookFile().then(function(L){
    look=L;if(L===null&&mode==='look'){mode='life';o.writeHash();}
    setTimeout(function(){
      if(me!==run)return;
      var P=S.P,t0=performance.now(),m=LM.build({pos:P.pos,n:P.n,tax:P.tax,grp:P.grp,groups:S.META.groups.length,
        color:o.color,T:S.TAXA,ranks:S.META.ranks,A:A,clade:r,look:L,src:P.src});
      console.info('map of life built in '+Math.round(performance.now()-t0)+' ms');
      o.status('');
      if(!m){if(r>=0)draw(-1,true);else{M=null;bar();o.redraw();}return;}  // too few records: points alone
      if(m.look)m.lookC=canvas(m,m.look);
      m.imgC=canvas(m,m.image);
      if(cache.size>8)cache.clear();
      cache.set(r,m);show(m,fit);
    },20);
  });
}
function show(m,fit){
  M=m;placed=null;bar();
  // with room around the land for the kingdom labels
  var e=m.ext,p=.1*Math.max(e[2]-e[0],e[3]-e[1]);
  if(fit)o.frame([e[0]-p,e[1]-p,e[2]+p,e[3]+p]);
  o.redraw();
}
function set(m){
  if(m==='look'&&look===null)return;
  mode=m;bar();o.writeHash();o.redraw();
}
function go(r){if(r!==row)draw(r,true);}
$('vclade').addEventListener('click',function(){set('life');});
$('vlook').addEventListener('click',function(){set('look');});
$('lup').addEventListener('click',function(){go(LM.parentOf(A,S.TAXA,S.META.ranks,row));});

function text(t){
  if(!on())return null;
  if(t.layer&&t.layer.id.indexOf('life-lbl')===0&&t.object)return name(t.object.row);
  var h=t.coordinate&&LM.hit(M,t.coordinate[0],t.coordinate[1]);
  if(!h||h.sea)return '';
  if(h.outside)return 'Outside '+S.TAXA[row][0];
  var sl=M.slots[h.slot],out=[],fine=M.fine;
  if(sl.row>=0){
    out.push(name(sl.row),nf.format(sl.n)+' records');
    if(sl.agree!=null)out.push(Math.round(100*sl.agree)+'% of its photo neighbours are also '+S.TAXA[sl.row][0]);
  }else out.push('Other '+(fine==='class'?'classes':fine==='family'?'families':'orders'),nf.format(sl.n)+' records');
  if(mode==='look'&&h.levels){
    var tot=h.levels.reduce(function(a,b){return a+b;},0);
    if(tot)out.push('Closest look-alike here:');
    h.levels.forEach(function(v,i){if(tot&&v/tot>=.01)out.push('  '+Math.round(100*v/tot)+'% '+LM.LEVELS[i]);});
  }
  return out.join('\n');
}
// A click the points did not take: a label or a region zooms into its clade, outside the clade goes up.
function click(t){
  if(!on())return false;
  var r=-1;
  if(t.layer&&t.layer.id.indexOf('life-lbl')===0&&t.object)r=t.object.row;
  else{var h=t.coordinate&&LM.hit(M,t.coordinate[0],t.coordinate[1]);
    if(h&&h.outside){go(LM.parentOf(A,S.TAXA,S.META.ranks,row));return true;}
    if(h&&h.slot>=0)r=M.slots[h.slot].row;}
  if(r>=0&&LM.canZoom(S.TAXA,S.META.ranks,r))go(r);
  return true;
}
// The map, then pts (the app's points layer), then the labels that read at the view's zoom; the map dims while
// points are drawn over it.
function layers(pts,dim){
  var z=Math.round(S.vs.zoom*4)/4;
  if(!placed||placed.z!==z)placed={z:z,L:LM.place(M.labels,z,MIN_PX)};
  function lbl(id,data,weight){
    return new deck.TextLayer({id:id,data:data,getPosition:function(d){return d.pos;},getText:function(d){return d.text;},
      getSize:function(d){return d.size;},sizeUnits:'common',sizeMaxPixels:weight==='800'?22:30,
      fontFamily:'system-ui,-apple-system,"Segoe UI",sans-serif',fontWeight:weight,characterSet:'auto',
      getColor:[29,29,27,235],fontSettings:{sdf:true},outlineWidth:3,outlineColor:[255,255,255,220],pickable:true});
  }
  var L=placed.L,b=[M.ext[0],M.ext[1],M.ext[2],M.ext[3]];
  return [new deck.BitmapLayer({id:'life-img',image:mode==='look'&&M.lookC?M.lookC:M.imgC,bounds:b,opacity:dim?.4:1}),pts,
    lbl('life-lbl',L.filter(function(d){return !d.italic&&!d.bold;}),'600'),
    lbl('life-lbl-i',L.filter(function(d){return d.italic;}),'italic 500'),
    lbl('life-lbl-k',L.filter(function(d){return d.bold;}),'800')];
}
// The view's tokens replace any already in the hash list h.
function hash(h){
  h=h.filter(function(t){var k=t.split('=')[0];return k!=='life'&&k!=='clade';});
  if(mode==='look')h.push('life=look');
  if(row>=0)h.push('clade='+S.TAXA[row][2]);
  return h;
}
// The join brings the names and the rows the map needs, and the map is drawn then; a subset or an opened record
// keeps its own view.
function joined(){
  if(!S.TAXA||!S.META)return;
  A=LM.ancestors(S.TAXA,S.META.ranks);byId=new Map();
  S.TAXA.forEach(function(t,i){byId.set(t[2],i);});
  cache.clear();M=null;$('lifebar').hidden=false;
  var r=want&&byId.has(want)?byId.get(want):-1;want=0;
  if(r>=0&&!LM.canZoom(S.TAXA,S.META.ranks,r))r=-1;
  draw(r,!S.subset&&S.sel<0);
}
return {on:on,layers:layers,text:text,click:click,hash:hash,joined:joined};
}
