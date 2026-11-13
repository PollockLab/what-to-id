// Level 3 controls and blitz gaps. The confidence filter keeps the Top 1%, 5% (the default), 25% or all of the level by its rank
// band (hash conf=1|5|25|all); the sort toggles Confidence and Blitz gaps, both on by default (hash sort=conf or sort=gaps, absent for both,
// the last one on cannot be turned off): both is the blend (band minus gap tier, then band, then rank), Confidence strict rank, Blitz gaps
// the gap tier then rank. Gaps come from where-to-blitz's checklist layer (one 25 km PNG per group, read at run time): a record in a cell
// short of the 30 observer-days of a checklist gets a gap tier (2 under half, 1 under 30, 0 lit or no data) and a badge.
// IdentifyGaps(ctx), ctx {P, groups (META.groups), keep(i) the records to read, band(i) 0..3, redraw(late) with late true when records arrived}. A failed load leaves every gap at 0.
var IdentifyGaps=(function(){
'use strict';
var BASE='https://pollocklab.github.io/where-to-blitz/',DIR=BASE+'cluster_results/checklist/',RES='25000',ALL='All biodiversity',
  LIMS=[['1','Top 1%'],['5','Top 5%'],['25','Top 25%'],['all','All']];
function $(id){return document.getElementById(id);}
function el(tag,cls,text){var e=document.createElement(tag);if(cls)e.className=cls;if(text!=null)e.textContent=text;return e;}
// where-to-blitz's Lambert azimuthal equal area (WGS 84, centre 45N 100W) forward: [x, y] metres of lat, lon in degrees
var fwd=(function(){
  var A=6378137,ES=0.0066943799901413165,E=Math.sqrt(ES),RAD=Math.PI/180;
  function q(s){var c=E*s;return (1-ES)*(s/(1-c*c)-(0.5/E)*Math.log((1-c)/(1+c)));}
  var QP=q(1),RQ=Math.sqrt(0.5*QP),S0=Math.sin(45*RAD),SB1=q(S0)/QP,CB1=Math.sqrt(1-SB1*SB1),
    DD=Math.cos(45*RAD)/(Math.sqrt(1-ES*S0*S0)*RQ*CB1),L0=-100*RAD;
  return function(lat,lon){
    var lam=lon*RAD-L0,sb=q(Math.sin(lat*RAD))/QP,cb=Math.sqrt(1-sb*sb),b=Math.sqrt(2/(1+SB1*sb+CB1*cb*Math.cos(lam)));
    return [A*RQ*DD*b*cb*Math.sin(lam),A*RQ/DD*b*(CB1*sb-SB1*cb*Math.cos(lam))];};
})();
function json(url){return fetch(url).then(function(r){if(!r.ok)throw new Error('HTTP '+r.status);return r.json();});}
// a PNG's pixels as {w, h, d} RGBA; the cells that matter are opaque, so premultiplying costs nothing
function png(url){
  return fetch(url).then(function(r){if(!r.ok)throw new Error('HTTP '+r.status);return r.blob();})
    .then(function(b){return createImageBitmap(b,{premultiplyAlpha:'none'});}).then(function(im){
      var c=document.createElement('canvas');c.width=im.width;c.height=im.height;
      var x=c.getContext('2d',{willReadFrequently:true});x.drawImage(im,0,0);
      return {w:im.width,h:im.height,d:x.getImageData(0,0,im.width,im.height).data};});
}
return function(ctx){
  var P=ctx.P,h=location.hash.slice(1),sm=/(?:^|&)sort=([\w,]*)/.exec(h),cm=/(?:^|&)conf=(\w+)/.exec(h),
    list=sm?sm[1].split(','):['conf','gaps'],byConf=list.indexOf('conf')>=0,byGaps=list.indexOf('gaps')>=0,
    lim=Math.max(0,LIMS.map(function(l){return l[0];}).indexOf(cm?cm[1]:'5')),state='load',tier=null,days=null,names=null,LSEG,TSEG,note;
  if(!byConf&&!byGaps)byConf=byGaps=true;
  function load(){
    json(DIR+'checklist.json').then(function(j){
      var t=j&&j.schema_version===3&&j.tiers&&j.tiers[RES],L=t&&t.lattice,lit=j&&j.rule_of_thumb_units;
      if(!L||!(lit>0))throw new Error('unexpected sidecar');
      var gs=ctx.groups.map(function(g){return t.groups[g]?g:ALL;}),used=[],pic={};
      for(var i=0;i<P.n;i++)if(ctx.keep(i)&&used.indexOf(gs[P.grp[i]])<0)used.push(gs[P.grp[i]]);
      return Promise.all(used.map(function(g){return png(DIR+t.groups[g].png).then(function(v){
        if(v.w!==L.ncol||v.h!==L.nrow)throw new Error('lattice mismatch');pic[g]=v;});})).then(function(){
        var tr=new Uint8Array(P.n),dy=new Uint16Array(P.n).fill(65535),nm=[];
        for(i=0;i<P.n;i++){
          if(!ctx.keep(i))continue;
          var g=gs[P.grp[i]],v=pic[g],f=fwd(P.lonlat[2*i+1],P.lonlat[2*i]),
            col=Math.floor((f[0]-L.x0)/L.res_m),row=Math.floor((L.y1-f[1])/L.res_m);
          if(col<0||row<0||col>=v.w||row>=v.h)continue;
          var k=(row*v.w+col)*4,a=v.d[k+3];
          if(a<32)continue;  // outside Canada: no data
          var d=a<128?0:v.d[k+1]*256+v.d[k+2];  // a Canadian cell without a record of the group has no observer-days
          dy[i]=d;tr[i]=d>=lit?0:d<lit/2?2:1;nm[i]=[g,lit];
        }
        tier=tr;days=dy;names=nm;state='ready';});
    }).catch(function(){state='failed';}).then(function(){ctx.redraw(true);});
  }
  function hash(){
    var t=location.hash.slice(1).split('&').filter(function(x){return x&&!/^(sort|conf)=/.test(x);});
    if(!(byConf&&byGaps))t.push('sort='+(byConf?'conf':'gaps'));
    if(lim!==1)t.push('conf='+LIMS[lim][0]);
    history.replaceState(null,'','#'+t.join('&'));
  }
  // a radio-like row of buttons (kind 'radio', one on) or checkbox-like (kind 'checkbox', each on or off); arrow keys move between them
  function seg(label,name,kind,labels,click){
    var r=el('div','seg');r.setAttribute('role',kind==='radio'?'radiogroup':'group');r.setAttribute('aria-label',name);
    labels.forEach(function(x,j){
      var b=el('button','segb',x);b.type='button';b.setAttribute('role',kind);b.onclick=function(){click(j);hash();ctx.redraw();};
      r.appendChild(b);});
    r.onkeydown=function(e){
      var k=['ArrowLeft','ArrowUp','ArrowRight','ArrowDown'].indexOf(e.key),all=[].slice.call(r.children),at=all.indexOf(document.activeElement);
      if(k<0||at<0)return;e.preventDefault();
      all[(at+(k%4<2?-1:1)+all.length)%all.length].focus();
    };
    var row=el('div','srow');row.append(el('span',null,label),r);
    return {row:row,seg:r};
  }
  function build(){
    var g=$('sort'),o=$('sorto');
    if(!g||!o)return;
    LSEG=seg('Confidence: ','Confidence','radio',LIMS.map(function(l){return l[1];}),function(j){lim=j;});
    TSEG=seg('Sort: ','Sort','checkbox',['Confidence','Blitz gaps'],function(j){  // the last one on stays on
      if(j===0&&byConf&&!byGaps||j===1&&byGaps&&!byConf)return;
      if(j===0)byConf=!byConf;else byGaps=!byGaps;});
    note=el('span','segnote');
    g.append(LSEG.row);o.append(TSEG.row,note);
  }
  build();
  load();
  return {
    // how level 3 is ordered: 0 strict rank, 1 the blend, 2 gap tier then rank (the blends need the checklist read)
    mode:function(){return byGaps&&state==='ready'?byConf?1:2:0;},
    // a record the confidence filter keeps
    pass:function(i){return ctx.band(i)<=lim;},
    // 0 lit or no data, 1 a gap, 2 a big gap
    tier:function(i){return tier?tier[i]:0;},
    // the gap badge of a record in a gap, else null: a link to where-to-blitz at the record's cell
    badge:function(i){
      var t=tier?tier[i]:0;
      if(!t)return null;
      var a=el('a','gap','Gap '+days[i]+'/'+names[i][1]),full='Blitz gap: '+days[i]+' of '+names[i][1]+' observer-days in this 25 km cell';
      a.href=BASE+'?at='+P.lonlat[2*i+1].toFixed(3)+','+P.lonlat[2*i].toFixed(3)+'&res='+RES+'&g='+encodeURIComponent(names[i][0])+'&goal=cl';
      a.target='_blank';a.rel='noopener';a.title=full+'; '+names[i][1]+' make a checklist (where-to-blitz)';a.setAttribute('aria-label',full);
      return a;
    },
    // the confidence filter's name for the count line, '' for all
    label:function(){return lim===3?'':LIMS[lim][1];},
    // the controls, shown on level 3 only
    draw:function(lv,sel,level){
      if(!LSEG)return;
      $('sort').hidden=$('sortb').hidden=lv!==3;
      if(lv!==3)return;
      [].forEach.call(LSEG.seg.children,function(x,j){x.setAttribute('aria-checked',String(j===lim));x.tabIndex=j===lim?0:-1;});
      [].forEach.call(TSEG.seg.children,function(x,j){x.setAttribute('aria-checked',String(j?byGaps:byConf));});
      note.textContent=state==='failed'?'The where-to-blitz checklist did not load. Listing by confidence.':state==='load'&&byGaps?
        'Loading the where-to-blitz checklist…':byConf&&byGaps?'Both on: confidence and gaps blended.':'';
    }
  };
};
})();
