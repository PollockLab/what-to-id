// Prioritize: how the cards of every level are ordered and cut. Two filters: the confidence band (Top x% of level 3 by its rank, hash conf=1..100,
// all or 100 for everything) and the blitz gap ceiling (observer-days of a cell at most N, hash gap=0..30, absent off). Five prioritizers, each with a
// weight 0 (off) to 3, add up to one score (hash pri=conf:2,gap:1, pri=none for all off, absent conf:1,gap:1; the old sort=conf and sort=gaps still read):
// Confidence (level 3 by its rank, else the score bucket), Blitz gap (tier 2 under half, 1 under 30, 0 lit or no data), At risk, Invasive, Outside range.
// Ties go to the confidence order when base= is absent and a prioritizer is on, else to the base order (hash base=new|old|rand:<seed>, Newest by default).
// Gaps come from where-to-blitz's checklist layer (one 25 km PNG per group, read at run time) for every record of every level. A failed load leaves every gap at 0.
// IdentifyGaps(ctx), ctx {P, groups (META.groups), keep(i) the records to read, pct(i) the place of a level 3 record in its level 0..1, band(i) 0..3,
// hasRank(), conf(i,lv) and fine(i,lv) the confidence score 0..3 and its finer order (higher better), flag(i,inv) 1 at risk | 2 invasive, hasOut(), out(i) 1 far
// outside its range, redraw(late) with late true when records arrived}. IdentifyGaps.compare(o) is the pure comparator.
var IdentifyGaps=(function(){
'use strict';
var BASE='https://pollocklab.github.io/where-to-blitz/',DIR=BASE+'cluster_results/checklist/',RES='25000',ALL='All biodiversity',
  KEYS=['conf','gap','risk','inv','out'],WORDS=['Off','Low','Medium','High'],DEFAULT={conf:1,gap:1,risk:0,inv:0,out:0},
  NAMES={conf:['Confidence','most confident'],gap:['Blitz gap','biggest blitz gaps'],risk:['At risk','at-risk species'],inv:['Invasive','invasive species'],
    out:['Outside range','records outside their range']},
  BASES={new:'newest first',old:'oldest first',rand:'random order'},NODAYS=65535;
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
// the inverse of fwd by Newton steps from a nearby lat, lon: [lon, lat]
function inv(x,y,la,lo){
  for(var k=0;k<8;k++){
    var f=fwd(la,lo),ex=x-f[0],ey=y-f[1],h=1e-5,a=fwd(la+h,lo),b=fwd(la,lo+h),
      j11=(b[0]-f[0])/h,j12=(a[0]-f[0])/h,j21=(b[1]-f[1])/h,j22=(a[1]-f[1])/h,d=j11*j22-j12*j21;
    if(Math.abs(ex)+Math.abs(ey)<0.01)break;
    lo+=(ex*j22-ey*j12)/d;la+=(j11*ey-j21*ex)/d;
  }
  return [lo,la];
}
function json(url){return fetch(url).then(function(r){if(!r.ok)throw new Error('HTTP '+r.status);return r.json();});}
// a PNG's pixels as {w, h, d} RGBA; the cells that matter are opaque, so premultiplying costs nothing
function png(url){
  return fetch(url).then(function(r){if(!r.ok)throw new Error('HTTP '+r.status);return r.blob();})
    .then(function(b){return createImageBitmap(b,{premultiplyAlpha:'none'});}).then(function(im){
      var c=document.createElement('canvas');c.width=im.width;c.height=im.height;
      var x=c.getContext('2d',{willReadFrequently:true});x.drawImage(im,0,0);
      return {w:im.width,h:im.height,d:x.getImageData(0,0,im.width,im.height).data};});
}
// A comparator that leaves the best last: o {key (the groups of the level's order), score, fine (or null), base 'new'|'old'|'rand', seed, id}, arrays by record.
function compare(o){
  function rnd(i){var x=(o.id[i]^o.seed)>>>0;x=Math.imul(x^x>>>16,0x45d9f3b)>>>0;x=Math.imul(x^x>>>16,0x45d9f3b)>>>0;return (x^x>>>16)>>>0;}
  return function(x,y){
    return o.key[x]-o.key[y]||o.score[x]-o.score[y]||(o.fine?o.fine[x]-o.fine[y]:0)||
      (o.base==='old'?o.id[y]-o.id[x]:o.base==='rand'?rnd(x)-rnd(y):o.id[x]-o.id[y]);};
}
// the state in the hash: top (conf=), gap (gap=), w (pri=, else the old sort=), base and seed (base=)
function read(){
  var h=location.hash.slice(1),w=Object.assign({},DEFAULT);
  function m(k){var r=new RegExp('(?:^|&)'+k+'=([^&]*)').exec(h);return r?decodeURIComponent(r[1]):null;}
  var c=m('conf'),g=m('gap'),p=m('pri'),s=m('sort'),b=m('base'),top=c==='all'?100:Math.round(+c);
  if(p!=null){
    KEYS.forEach(function(k){w[k]=0;});
    p.split(',').forEach(function(t){var kv=t.split(':');if(kv[0] in w)w[kv[0]]=Math.max(0,Math.min(3,Math.round(+kv[1])||0));});
  }else if(s!=null){
    var l=s.split(',');
    if(l.indexOf('conf')<0||l.indexOf('gaps')<0){w.conf=+(l.indexOf('conf')>=0);w.gap=+(l.indexOf('gaps')>=0);}
  }
  var bm=b&&/^(?:(new|old)|rand:(\d+))$/.exec(b);
  return {top:top>=1&&top<=100?top:5,gap:g!=null&&g!==''&&isFinite(g)?Math.max(0,Math.min(30,Math.round(+g))):null,w:w,
    base:bm?bm[1]||'rand':'new',seed:bm&&bm[2]?+bm[2]:1,explicit:!!bm};
}
var F=function(ctx){
  var P=ctx.P,st=read(),state='load',settle,ready=new Promise(function(r){settle=r;}),tier=null,days=null,names=null,cells=null,LAT=null,LIT=30,UI=null,T=0;
  function alloff(){return !KEYS.some(function(k){return st.w[k]>0;});}
  function isdef(){return st.top===5&&st.gap==null&&!st.explicit&&KEYS.every(function(k){return st.w[k]===DEFAULT[k];});}
  function load(){
    json(DIR+'checklist.json').then(function(j){
      var t=j&&j.schema_version===3&&j.tiers&&j.tiers[RES],L=t&&t.lattice,lit=j&&j.rule_of_thumb_units;
      if(!L||!(lit>0))throw new Error('unexpected sidecar');
      var gs=ctx.groups.map(function(g){return t.groups[g]?g:ALL;}),used=[],pic={};
      for(var i=0;i<P.n;i++)if(ctx.keep(i)&&used.indexOf(gs[P.grp[i]])<0)used.push(gs[P.grp[i]]);
      return Promise.all(used.map(function(g){return png(DIR+t.groups[g].png).then(function(v){
        if(v.w!==L.ncol||v.h!==L.nrow)throw new Error('lattice mismatch');pic[g]=v;});})).then(function(){
        var tr=new Uint8Array(P.n),dy=new Uint16Array(P.n).fill(NODAYS),nm=[],cl=new Int32Array(P.n).fill(-1);
        for(i=0;i<P.n;i++){
          if(!ctx.keep(i))continue;
          var g=gs[P.grp[i]],v=pic[g],f=fwd(P.lonlat[2*i+1],P.lonlat[2*i]),
            col=Math.floor((f[0]-L.x0)/L.res_m),row=Math.floor((L.y1-f[1])/L.res_m);
          if(col<0||row<0||col>=v.w||row>=v.h)continue;
          var k=(row*v.w+col)*4,a=v.d[k+3];
          if(a<32)continue;  // outside Canada: no data
          var d=a<128?0:v.d[k+1]*256+v.d[k+2];  // a Canadian cell without a record of the group has no observer-days
          dy[i]=d;tr[i]=d>=lit?0:d<lit/2?2:1;nm[i]=[g,lit];cl[i]=row*v.w+col;
        }
        tier=tr;days=dy;names=nm;cells=cl;LAT=L;LIT=lit;state='ready';});
    }).catch(function(){state='failed';}).then(function(){ctx.redraw(true);settle();});
  }
  // the hash holds only what differs from the defaults
  function hash(){
    var t=location.hash.slice(1).split('&').filter(function(x){return x&&!/^(sort|conf|gap|pri|base)=/.test(x);});
    if(st.top!==5)t.push('conf='+(st.top===100?'all':st.top));
    if(st.gap!=null)t.push('gap='+st.gap);
    if(!KEYS.every(function(k){return st.w[k]===DEFAULT[k];}))
      t.push('pri='+(alloff()?'none':KEYS.filter(function(k){return st.w[k];}).map(function(k){return k+':'+st.w[k];}).join(',')));
    if(st.explicit)t.push('base='+(st.base==='rand'?'rand:'+st.seed:st.base));
    history.replaceState(null,'','#'+t.join('&'));
  }
  // the hash at once, the redraw after wait ms (a slider drags on without redrawing every step)
  function change(wait){
    hash();clearTimeout(T);
    T=setTimeout(function(){ctx.redraw();},wait||0);
  }
  function applies(k,lv){return k==='risk'||k==='inv'?lv===3:k==='out'?!!ctx.hasOut():true;}
  function score(i,lv){
    var w=st.w,s=0;
    if(w.conf)s+=w.conf*ctx.conf(i,lv);
    if(w.gap&&tier)s+=w.gap*tier[i];
    if(lv===3&&(w.risk||w.inv)){var f=ctx.flag(i,!!w.inv);s+=w.risk*(f&1)+w.inv*(f>>1&1);}
    if(w.out&&ctx.hasOut())s+=w.out*ctx.out(i);
    return s;
  }
  function summary(lv){
    var on=KEYS.filter(function(k){return st.w[k]&&applies(k,lv);}).sort(function(a,b){return st.w[b]-st.w[a];}),base=BASES[st.base];
    if(!on.length)return base[0].toUpperCase()+base.slice(1)+' (no prioritizers)';
    var t=on.map(function(k){return NAMES[k][1];}),r=t[0][0].toUpperCase()+t[0].slice(1)+' first'+t.slice(1).map(function(x){return ', then '+x;}).join('');
    return st.explicit?r+', then '+base:r;
  }
  function slider(id,min,max,txt){
    var r=el('div','prow2'),l=el('label'),i=el('input'),b=el('b');
    l.htmlFor=id;i.type='range';i.id=id;i.min=min;i.max=max;i.step=1;l.append(txt+' ',b);r.append(l,i);
    return {row:r,input:i,out:b};
  }
  // the filters and prioritizers in #sorto; draw hides the ones a level has no data for
  function build(){
    var o=$('sorto');
    if(!o)return;
    var sum=el('p','segnote'),top=slider('ptop',1,100,'Top'),gp=slider('pgap',0,31,'Blitz gap at most'),dl=el('datalist'),sel={},rows={};
    sum.id='psum';sum.setAttribute('aria-live','polite');
    dl.id='ptl';[1,5,25,100].forEach(function(v){var x=el('option');x.value=v;dl.appendChild(x);});
    top.input.setAttribute('list','ptl');
    top.input.oninput=function(){st.top=+top.input.value;change(150);};
    gp.input.oninput=function(){st.gap=+gp.input.value>30?null:+gp.input.value;change(150);};
    var pr=el('div','pgrp'),fl=el('div','pgrp');
    pr.appendChild(el('p','phead','Prioritize'));fl.append(el('p','phead','Filters'),top.row,dl,gp.row);
    KEYS.forEach(function(k){
      var r=el('div','prow2'),l=el('label',null,NAMES[k][0]),s=el('select');
      l.htmlFor=s.id='pw-'+k;
      WORDS.forEach(function(x,j){var op=el('option',null,x);op.value=j;s.appendChild(op);});
      s.onchange=function(){st.w[k]=+s.value;change();};
      r.append(l,s);sel[k]=s;rows[k]=r;pr.appendChild(r);});
    var bs=el('select'),br=el('div','prow2'),bl=el('label',null,'Then by'),sh=el('button','lnk','Shuffle'),rs=el('button','lnk','Reset to defaults');
    bl.htmlFor=bs.id='pbase';sh.type=rs.type='button';rs.id='preset';
    [['new','Newest first'],['old','Oldest first'],['rand','Random']].forEach(function(x){var op=el('option',null,x[1]);op.value=x[0];bs.appendChild(op);});
    bs.onchange=function(){st.base=bs.value;st.explicit=true;if(st.base==='rand')st.seed=1+Math.floor(Math.random()*1e6);change();};
    sh.onclick=function(){st.seed=1+Math.floor(Math.random()*1e6);change();};
    rs.onclick=function(){st=Object.assign(read(),{top:5,gap:null,w:Object.assign({},DEFAULT),base:'new',explicit:false});change();};
    br.append(bl,bs,sh);
    o.append(sum,fl,pr,br,rs);
    UI={sum:sum,top:top,gap:gp,sel:sel,rows:rows,base:bs,shuffle:sh,reset:rs};
  }
  build();
  load();
  return {
    ready:ready,  // settles once the checklist has loaded or failed and the redraw is done
    // a record the filters keep: level 3's Top x% and every level's blitz gap ceiling
    pass:function(i,kind){
      if(kind===3&&st.top<100){var p=ctx.pct(i);if(p!=null&&p>st.top/100)return false;}
      return st.gap==null||state!=='ready'||days[i]<=st.gap;
    },
    // the 25 km cell of a record (its lattice index, -1 without data), its observer-days, the cell's lit count, and the cell as a flat lon, lat ring
    cell:function(i){return cells?cells[i]:-1;},
    days:function(i){return days?days[i]:NODAYS;},
    lit:function(){return LIT;},
    ring:function(i){
      var c=cells[i],L=LAT,x=L.x0+(c%L.ncol)*L.res_m,y=L.y1-Math.floor(c/L.ncol)*L.res_m,s=L.res_m,out=[],q=8,k,
        C=[[x,y,s/q,0],[x+s,y,0,-s/q],[x+s,y-s,-s/q,0],[x,y-s,0,s/q]];
      C.forEach(function(e){for(k=0;k<q;k++){var p=inv(e[0]+e[2]*k,e[1]+e[3]*k,P.lonlat[2*i+1],P.lonlat[2*i]);out.push(p[0],p[1]);}});
      return out;
    },
    // a mission's score for a record at level lv: the gap tier, then at risk (level 3), then confidence, under the default Blitz the gap weights
    mission:function(i,lv){return 100*(tier?tier[i]:0)+(lv===3?10*(ctx.flag(i,false)&1):0)+ctx.conf(i,lv);},
    atRisk:function(i,lv){return lv===3&&(ctx.flag(i,false)&1)===1;},
    loaded:function(){return state==='ready';},
    // 0 lit or no data, 1 a gap, 2 a big gap
    tier:function(i){return tier?tier[i]:0;},
    // orders a level's records (a typed-array slice), the best last, under key (the groups of the level's order) and the prioritizers
    sort:function(ord,lv,key){
      var sc=new Float64Array(P.n),fn=null,k,i,fine=st.w.conf>0||!st.explicit&&!alloff();
      for(k=0;k<ord.length;k++)sc[ord[k]]=score(ord[k],lv);
      if(fine){fn=new Float64Array(P.n);for(k=0;k<ord.length;k++){i=ord[k];fn[i]=ctx.fine(i,lv);}}
      ord.sort(compare({key:key,score:sc,fine:fn,base:st.base,seed:st.seed,id:P.id}));
    },
    // the gap badge of a record in a gap, else null: the badge keeps the cells with that many days or fewer, the arrow opens where-to-blitz at the cell
    badge:function(i){
      var t=tier?tier[i]:0;
      if(!t)return null;
      var w=el('span','gapw'),b=el('button','gap','Gap '+days[i]+'/'+names[i][1]),a=el('a','gapx','↗'),
        full='Blitz gap: '+days[i]+' of '+names[i][1]+' observer-days in this 25 km cell';
      b.type='button';b.title=full+'. Click to keep cells with '+days[i]+' or fewer';b.setAttribute('aria-label',full+'. Keep cells with '+days[i]+' or fewer');
      b.onclick=function(){st.gap=days[i];change();};
      a.href=BASE+'?at='+P.lonlat[2*i+1].toFixed(3)+','+P.lonlat[2*i].toFixed(3)+'&res='+RES+'&g='+encodeURIComponent(names[i][0])+'&goal=cl';
      a.target='_blank';a.rel='noopener';a.title=names[i][1]+' make a checklist (where-to-blitz)';a.setAttribute('aria-label','Open this cell in where-to-blitz');
      w.append(b,a);return w;
    },
    // a level 3 record's "Top 1%" badge: a click keeps that band
    confBadge:function(i,text){
      var b=el('button','conf',text),n=[1,5,25][ctx.band(i)];
      b.type='button';b.title='Click to keep the Top '+n+'%';b.onclick=function(){st.top=n;change();};
      return b;
    },
    // the filters' names for the count line
    label:function(){return st.top<100?'Top '+st.top+'%':'';},
    gaplabel:function(){return st.gap!=null&&state==='ready'?'gap '+st.gap+' days or fewer':'';},
    // the controls and the summary line, for level lv
    draw:function(lv){
      if(!UI)return;
      UI.top.row.hidden=!(lv===3&&ctx.hasRank());UI.top.input.value=st.top;UI.top.out.textContent=st.top+'%';
      var any=st.gap==null;
      UI.gap.input.value=any?31:st.gap;UI.gap.out.textContent=any?'(any)':st.gap+' observer-days';
      UI.gap.input.setAttribute('aria-valuetext',any?'any':st.gap+' observer-days');
      KEYS.forEach(function(k){UI.rows[k].hidden=!applies(k,lv);UI.sel[k].value=st.w[k];});
      UI.base.value=st.base;UI.shuffle.hidden=st.base!=='rand';UI.reset.hidden=isdef();
      UI.sum.textContent=summary(lv)+(state==='load'&&(st.w.gap||st.gap!=null)?' (reading the where-to-blitz checklist…)':
        state==='failed'?'. The where-to-blitz checklist did not load, so gaps are ignored.':'');
      $('sortb').hidden=false;
    }
  };
};
F.compare=compare;
return F;
})();
