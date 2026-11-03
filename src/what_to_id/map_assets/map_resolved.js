// The records that left Needs ID in the last 7 or 30 days (pool-resolved.bin, format in map_resolved.py), counted and drawn
// under the map's own filters: the same MapFilter.keep and rest and group chips the records of the pool pass through, then
// the areas. They are not records of the map (no filter on the GPU), so nothing else the map counts includes them.
// Decoded days are the map's (from META.day0); the left day and the build day stay in days since 1900-01-01.
function leftDecode(buf,shift,LAST){
  var n=(buf.byteLength-8)/23,o=8,v=new DataView(buf);
  if(buf.byteLength<8||n%1)throw new Error('unexpected size');
  function col(T){var a=new T(buf,o,n);o+=n*T.BYTES_PER_ELEMENT;return a;}
  function day(a){return Uint16Array.from(a,function(x){return x===65535||x<shift||x-shift>LAST?65535:x-shift;});}
  var R={n:n,start:v.getUint16(0,true),build:v.getUint16(2,true),live:v.getUint16(4,true),id:col(Uint32Array),lon:col(Float32Array),lat:col(Float32Array)};
  R.obs=day(col(Uint16Array));R.up=day(col(Uint16Array));R.left=col(Uint16Array);R.tax=col(Uint16Array);
  R.grp=col(Uint8Array);R.flags=col(Uint8Array);R.reason=col(Uint8Array);
  return R;
}
// 1 per record that left within win days of the build and that the taxa, groups, dates, months, show only chips and areas
// keep. TF is TX.filter's result, groups META.groups and areas the loaded areas' indexes (MapArea.index).
function leftKeep(MF,CH,groups,S,TF,R,areas,win){
  var n=R.n,out=MF.keep(TF,MF.groupSet(S,TF),R.tax,R.grp,n,new Uint8Array(n)),ok=CH.groupPass(S.groups,groups,!!TF.inc),i,j;
  for(i=0;i<n;i++)if(!ok[R.grp[i]]||R.left[i]<=R.build-win)out[i]=0;
  MF.rest(S,R.obs,R.up,R.flags,n,out);
  if(areas.length)for(i=0;i<n;i++)if(out[i]){out[i]=0;
    for(j=0;j<areas.length;j++)if(MapArea.inside(areas[j],R.lon[i],R.lat[i])){out[i]=1;break;}}
  return out;
}
// The control's lines for k records (rg of them Research Grade) that left within win days of the build, from the log's own
// days: {text, tip, note}. It says "in the last N days" only when the log reaches back that far, else "since" its first day;
// tip is the exact window; note is the Research Grade-only stretch (records backfilled before the live log began), set only
// while the window reaches into it. fmt(day, withYear) formats a day as "3 Nov" or "3 Nov 2026".
function leftSay(k,rg,inView,win,R,fmt,nf){
  var from=Math.max(R.build-win+1,R.start),full=R.build-win+1>=R.start;
  return {text:nf.format(k)+(inView?' in view':'')+' left Needs ID '+(full?'in the last '+win+' days':'since '+fmt(from))+
      (rg?', '+nf.format(rg)+' as Research Grade':''),
    tip:fmt(from)+' to '+fmt(R.build,1)+', UTC',
    note:from<R.live?'Before '+fmt(R.live)+' only Research Grade is counted.':''};
}
function leftFilter(o){
  var S=o.S,MF=o.MF,META=o.meta,box=document.getElementById('leftbox'),nf=new Intl.NumberFormat('en-CA'),
    shift=(MF.D0-Date.UTC(1900,0,1))/MF.DAY,w=+new URLSearchParams(location.hash.slice(1)).get('resolved'),
    win=w===7||w===30?w:0,R=null,err='',busy=false,C=null,msg,main,note,btns=[],
    MON='Jan Feb Mar Apr May Jun Jul Aug Sep Oct Nov Dec'.split(' ');
  function el(tag,cls,text){var e=document.createElement(tag);if(cls)e.className=cls;if(text!=null)e.textContent=text;return e;}
  function load(){
    if(!win||R||busy)return;busy=true;
    o.get('pool-resolved.bin'+String(META.shards[0].file).replace(/^[^?]*/,'')).then(function(b){R=leftDecode(b,shift,MF.LAST);})
      .catch(function(e){err='Could not load the records that left Needs ID ('+e.message+').';})
      .then(function(){busy=false;o.changed();});}
  // the kept records and their indexes, until a filter, area or window changes
  function calc(){
    if(!win||!R||o.off())return null;
    var k=[o.tf(),JSON.stringify([S.groups,S.only,S.up,S.lo,S.hi,S.months,S.acc]),o.area().ver(),win,R];
    if(C&&C.k.every(function(x,j){return x===k[j];}))return C;
    var m=leftKeep(MF,CH,META.groups,S,k[0],R,o.area().idx(),win),idx=[];
    for(var i=0;i<R.n;i++)if(m[i])idx.push(i);
    return C={k:k,idx:idx};}
  function set(v){win=v;err='';load();o.changed();}
  if(box){
    box.appendChild(el('span','muted','Left Needs ID '));
    var seg=box.appendChild(el('span','seg'));seg.setAttribute('role','group');seg.setAttribute('aria-label','Records that left Needs ID');
    [['Off',0],['7 days',7],['30 days',30]].forEach(function(b){var x=seg.appendChild(el('button',null,b[0]));x.type='button';
      x.title=b[1]?'Show the records that left Needs ID in the last '+b[1]+' days':'Hide them';x.onclick=function(){set(b[1]);};btns.push([x,b[1]]);});
    msg=box.appendChild(el('span'));main=msg.appendChild(el('span'));note=msg.appendChild(el('span','muted'));note.style.display='block';box.hidden=false;
  }
  load();
  return {
    hash:function(){return win?['resolved='+win]:[];},
    layers:function(){var c=calc();if(!c)return [];
      return [new deck.ScatterplotLayer({id:'left',data:c.idx,getPosition:function(i){return [R.lon[i],R.lat[i]];},
        radiusUnits:'pixels',getRadius:6,getFillColor:[200,0,120],stroked:true,lineWidthUnits:'pixels',getLineWidth:1.5,
        getLineColor:[255,255,255],pickable:true,
        onClick:function(x){if(x.object!=null)window.open('https://www.inaturalist.ca/observations/'+R.id[x.object],'_blank','noopener');}})];},
    render:function(){
      if(!box)return;
      btns.forEach(function(b){b[0].setAttribute('aria-pressed',String(b[1]===win));});
      var c=win&&R&&!o.off()?calc():null,t='',say=null;
      if(win&&err)t=err;else if(win&&!R)t='Loading…';
      else if(win&&!c)t='Not counted under the project, user, photo search or lasso filters.';
      else if(c){
        var b=o.all()?null:o.map().getBounds(),we=b&&b.getWest(),e=b&&b.getEast(),s=b&&b.getSouth(),nn=b&&b.getNorth(),k=0,rg=0;
        c.idx.forEach(function(i){var x=R.lon[i],y=R.lat[i];
          if(b&&(y<s||y>nn||(we<=e?x<we||x>e:x<we&&x>e)))return;k++;if(R.reason[i]===1||R.reason[i]===5)rg++;});
        say=leftSay(k,rg,!!b,win,R,function(d,y){var i=MF.iso(d-shift);return +i.slice(8)+' '+MON[i.slice(5,7)-1]+(y?' '+i.slice(0,4):'');},nf);t=say.text;}
      main.textContent=t;main.title=say?say.tip:'';note.textContent=say?say.note:'';}
  };
}
