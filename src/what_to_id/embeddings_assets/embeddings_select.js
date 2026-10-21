// Photo space: what narrows the points by where they are. The map's area and view arrive as ring lists and the
// lasso is drawn here; embeddings_app.js reads their verdicts through the functions this returns.
function SpaceSelect(S,$,picked,layers){
'use strict';
var AI=null,VI=null,DRAW=false;
// The points the dates, months, show only chips, the area and the lasso leave in, apart from the taxa and
// groups; null when none is set. An area that does not read is left to the map and shows as map only.
function areaIndex(){
  if(!S.area)return null;
  if(!AI||AI.key!==S.area){
    AI={key:S.area,I:null};
    try{var r=MapArea.decode(S.area);if(r.length)AI.I=MapArea.index(r);}catch(e){}
  }
  return AI.I;
}
// The view is a rectangle: its box [w,s,e,n], or null when absent or when it holds the whole data (it cuts nothing).
function viewBox(){
  if(!S.view)return null;
  if(!VI||VI.key!==S.view){
    VI={key:S.view,B:null};
    try{var r=MapArea.decode(S.view)[0],L=S.P.lonlat,d=S.dataBox;
      if(!d||d.P!==S.P){d=S.dataBox={P:S.P,b:[1/0,1/0,-1/0,-1/0]};
        for(var j=0;j<S.P.n;j++){var x=L[2*j],y=L[2*j+1];
          if(x<d.b[0])d.b[0]=x;if(x>d.b[2])d.b[2]=x;if(y<d.b[1])d.b[1]=y;if(y>d.b[3])d.b[3]=y;}}
      if(r){var w=Math.min(r[0],r[2],r[4]),e=Math.max(r[0],r[2],r[4]),so=Math.min(r[1],r[3],r[5]),n=Math.max(r[1],r[3],r[5]);
        if(!(w<=d.b[0]&&e>=d.b[2]&&so<=d.b[1]&&n>=d.b[3]))VI.B=[w,so,e,n];}}catch(er){}
  }
  return VI.B;
}
// The area's verdict per point, built once per area (panning re-runs applyBase but not this).
function areaMask(){
  var I=areaIndex(),P=S.P;
  if(!I)return null;
  if(!AI.M||AI.M.length!==P.n){AI.M=new Uint8Array(P.n);
    for(var i=0;i<P.n;i++)AI.M[i]=MapArea.inside(I,P.lonlat[2*i],P.lonlat[2*i+1]);}
  return AI.M;
}
// The map's projects: the sorted ids they keep (S.proj, null for none) as a verdict per point, built once per
// list by walking each shard's sorted rows against it.
var PM=null;
function projMask(){
  var P=S.P,ids=S.proj;
  if(!ids)return null;
  if(!PM||PM.ids!==ids||PM.m.length!==P.n){var m=new Uint8Array(P.n);
    for(var k=0;k+1<P.start.length;k++)for(var i=P.start[k],j=0;i<P.start[k+1]&&j<ids.length;i++){
      var v=P.id[i];while(j<ids.length&&ids[j]<v)j++;if(ids[j]===v)m[i]=1;}
    PM={ids:ids,m:m};}
  return PM.m;
}
// The lasso: a closed ring in layout coordinates, or null. Only the points inside it stay, and their ids go
// to the map, which keeps the same records.
function lasso(ring){
  var P=S.P,m=null,ids=null,i,k=0;
  S.ring=ring&&ring.concat(ring.slice(0,2));
  if(ring){var I=MapArea.index([ring]);m=new Uint8Array(P.n);
    for(i=0;i<P.n;i++)if(MapArea.inside(I,P.pos[2*i],P.pos[2*i+1])){m[i]=1;k++;}
    ids=new Uint32Array(k);k=0;for(i=0;i<P.n;i++)if(m[i])ids[k++]=P.id[i];}
  S.lasso=m;S.lassoV++;$('lclear').hidden=!ring;picked();send(true);
}
// Beside the map, the part of the space in view: its box [x0,y0,x1,y1] in layout coordinates, or null when it
// holds the home view's points or the map is not beside it. The map keeps its points, so each view narrows the other, never itself.
function shownBox(){
  var P=S.P,vs=S.vs,box=$('plot'),h=S.homeBox&&S.homeBox.b;
  if(!P||!vs||!h||parent===window||!document.documentElement.classList.contains('peer'))return null;
  var k=Math.pow(2,vs.zoom),hw=box.clientWidth/2/k,hh=box.clientHeight/2/k,b=[vs.target[0]-hw,vs.target[1]-hh,vs.target[0]+hw,vs.target[1]+hh];
  return b[0]<=h[0]&&b[1]<=h[1]&&b[2]>=h[2]&&b[3]>=h[3]?null:b;
}
function inBox(b,i){var x=S.P.pos[2*i],y=S.P.pos[2*i+1];return x>=b[0]&&x<=b[2]&&y>=b[1]&&y<=b[3];}
// The ids the lasso and the view both keep go to the map (null for all); a view that did not change sends nothing.
var SENT='',T=0;
function send(force){
  var P=S.P,b=shownBox(),key=b?b.join():'',ids=null,i,k=0;
  if((!force&&key===SENT)||parent===window)return;
  SENT=key;
  if(S.lasso||b){var m=new Uint8Array(P.n);
    for(i=0;i<P.n;i++)if((!S.lasso||S.lasso[i])&&(!b||inBox(b,i))){m[i]=1;k++;}
    ids=new Uint32Array(k);k=0;for(i=0;i<P.n;i++)if(m[i])ids[k++]=P.id[i];}
  parent.postMessage({type:'wtid-keep',ids:ids,view:!!b},location.origin);
}
function moved(){clearTimeout(T);T=setTimeout(send,250);}
$('lclear').addEventListener('click',function(){lasso(null);});
// The Draw button arms one lasso for pointers without a shift key (touch); it turns itself off after that drag.
var HINT='Drag around the photos to keep. Esc cancels.';
function draw(on){DRAW=on;$('ldraw').setAttribute('aria-pressed',String(on));$('plot').classList.toggle('draw',on);
  if(on)$('status').textContent=HINT;else if($('status').textContent===HINT)$('status').textContent='';}
$('ldraw').addEventListener('click',function(){draw(!DRAW);});
// Shift+drag, or a drag while Draw is on, draws one. The pointer is caught before deck.gl's controller sees it, so the view stays put.
// A drag too short to enclose anything, or Esc while drawing, leaves the lasso there was.
var cur=null,prev=null;
function cancel(){if(cur){cur=null;S.ring=prev;layers();}}
function lassoDrag(box){
  function at(e){var r=box.getBoundingClientRect(),p=S.deck.getViewports()[0].unproject([e.clientX-r.left,e.clientY-r.top]);
    return [p[0],p[1]];}
  box.addEventListener('pointerdown',function(e){
    if(!(e.shiftKey||DRAW)||e.button!==0||!S.P||!S.P.grp)return;
    e.stopPropagation();e.preventDefault();box.setPointerCapture(e.pointerId);prev=S.ring;cur=S.ring=at(e);layers();
  },true);
  box.addEventListener('pointermove',function(e){if(cur){cur.push.apply(cur,at(e));layers();}});
  ['pointerup','pointercancel'].forEach(function(t){box.addEventListener(t,function(){
    if(!cur)return;var r=cur;cur=null;draw(false);if(r.length>=6)lasso(r);else{S.ring=prev;layers();}});});
}
return {cancel:cancel,moved:moved,areaIndex:areaIndex,viewBox:viewBox,areaMask:areaMask,projMask:projMask,lasso:lasso,lassoDrag:lassoDrag,draw:draw};
}
