// Prioritize: how the cards of every level are ordered and cut. Two filters: Best x% (level 3 by its rank, hash conf=1..100, all or 100 for everything) and the
// survey days range (observer-days of a cell, hash gap=lo-hi, the old gap=n reads 0-n, absent or 0-30 off). Five prioritizers each carry a weight 0 (off) to 100 and
// add up to one score of weight x metric 0..1 (hash pri=conf:70,gap:100, pri=none for all off): Match (level 3 by its rank percentile, else the score bucket), Survey gap
// (1 - observer-days/30, 0 without data), At risk, Invasive and Out of range (0 or 1). The old pri values 0..3 read as 0, 33, 67, 100.
// A link without pri= keeps the tiered order it always had (hash sort=conf, sort=gaps and the default blend of the confidence band and the gap tier).
// Presets are sets of weights. Ties go to the confidence order when base= is absent and a prioritizer is on, else to the base order (hash base=new|old|rand:<seed>).
// Gaps come from where-to-blitz's checklist layer (one 25 km PNG per group, read at run time) for every record of every level. A failed load leaves every gap at 0.
// IdentifyGaps(ctx), ctx {P, groups (META.groups), keep(i) the records to read, pct(i) the place of a level 3 record in its level 0..1, band(i) 0..3,
// hasRank(), conf(i,lv) and fine(i,lv) the tiered confidence score 0..3 and its finer order (higher better), cont(i,lv) the confidence 0..1, flag(i,inv) 1 at risk | 2 invasive,
// hasOut(), out(i) 1 outside its range, redraw(late) with late true when records arrived}. IdentifyGaps.compare(o) is the pure comparator.
var IdentifyGaps=(function(){
'use strict';
var BASE='https://pollocklab.github.io/where-to-blitz/',DIR=BASE+'cluster_results/checklist/',RES='25000',ALL='All biodiversity',
  KEYS=['conf','gap','risk','inv','out'],LEG=[0,33,67,100],DEFAULT={conf:1,gap:1,risk:0,inv:0,out:0},LIT0=30,
  NAMES={conf:['Match','best matches'],gap:['Survey gap','biggest survey gaps'],risk:['At risk','at-risk species'],inv:['Invasive','invasive species'],
    out:['Out of range','records out of range']},
  EXPLAIN={conf:'best-match',gap:'survey-days'},
  PRESETS=[['blitz','Blitz the gap',{gap:100,risk:60,conf:40}],['quick','Quick wins',{conf:100}],['surprise','Surprises',{out:100,conf:40}],['newest','Newest',{}]],
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
// the state in the hash: top (conf=), gap (gap=), w (pri=, else the old sort=), base and seed (base=). legacy: no pri=, so w holds the old 0..3 levels.
function read(){
  var h=location.hash.slice(1),w=Object.assign({},DEFAULT),legacy=true;
  function m(k){var r=new RegExp('(?:^|&)'+k+'=([^&]*)').exec(h);return r?decodeURIComponent(r[1]):null;}
  var c=m('conf'),g=m('gap'),p=m('pri'),s=m('sort'),b=m('base'),top=c==='all'?100:Math.round(+c);
  if(p!=null){
    var v={};legacy=false;
    KEYS.forEach(function(k){w[k]=0;});
    p.split(',').forEach(function(t){var kv=t.split(':');if(kv[0] in w)v[kv[0]]=Math.max(0,Math.min(100,Math.round(+kv[1])||0));});
    var old=KEYS.every(function(k){return !(k in v)||v[k]<=3;});  // 0..3 are the old levels
    KEYS.forEach(function(k){if(k in v)w[k]=old?LEG[v[k]]:v[k];});
  }else if(s!=null){
    var l=s.split(',');
    if(l.indexOf('conf')<0||l.indexOf('gaps')<0){w.conf=+(l.indexOf('conf')>=0);w.gap=+(l.indexOf('gaps')>=0);}
  }
  var bm=b&&/^(?:(new|old)|rand:(\d+))$/.exec(b),gm=g&&/^(\d+)(?:-(\d+))?$/.exec(g),gap=null;
  if(gm){var lo=gm[2]==null?0:+gm[1],hi=Math.min(LIT0,gm[2]==null?+gm[1]:+gm[2]);if(lo>hi)lo=hi;gap=lo===0&&hi>=LIT0?null:[lo,hi];}
  return {top:top>=1&&top<=100?top:5,gap:gap,w:w,legacy:legacy,sort:p==null?s:null,
    base:bm?bm[1]||'rand':'new',seed:bm&&bm[2]?+bm[2]:1,explicit:!!bm};
}
var F=function(ctx){
  var P=ctx.P,st=read(),state='load',settle,ready=new Promise(function(r){settle=r;}),tier=null,days=null,names=null,LIT=LIT0,UI=null,T=0;
  function alloff(){return !KEYS.some(function(k){return st.w[k]>0;});}
  // the weight as the sliders show it, 0..100; the landing default shows as the Blitz the gap preset
  function disp(k){return isdef()?PRESETS[0][2][k]||0:st.legacy?LEG[st.w[k]]:st.w[k];}
  function toNew(){if(st.legacy){KEYS.forEach(function(k){st.w[k]=disp(k);});st.legacy=false;st.sort=null;}}  // a touched slider leaves the old tiered order
  function isdef(){return st.top===5&&st.gap==null&&!st.explicit&&st.legacy&&KEYS.every(function(k){return st.w[k]===DEFAULT[k];});}
  // the preset the weights are, null for Custom; the old default blend counts as Blitz the gap
  function preset(){
    if(isdef())return 'blitz';
    var hit=PRESETS.filter(function(x){return !st.legacy&&KEYS.every(function(k){return st.w[k]===(x[2][k]||0);})&&(x[0]!=='newest'||st.base==='new');})[0];
    return hit?hit[0]:null;
  }
  function load(){
    json(DIR+'checklist.json').then(function(j){
      var t=j&&j.schema_version===3&&j.tiers&&j.tiers[RES],L=t&&t.lattice,lit=j&&j.rule_of_thumb_units;
      if(!L||!(lit>0))throw new Error('unexpected sidecar');
      var gs=ctx.groups.map(function(g){return t.groups[g]?g:ALL;}),used=[],pic={};
      for(var i=0;i<P.n;i++)if(ctx.keep(i)&&used.indexOf(gs[P.grp[i]])<0)used.push(gs[P.grp[i]]);
      return Promise.all(used.map(function(g){return png(DIR+t.groups[g].png).then(function(v){
        if(v.w!==L.ncol||v.h!==L.nrow)throw new Error('lattice mismatch');pic[g]=v;});})).then(function(){
        var tr=new Uint8Array(P.n),dy=new Uint16Array(P.n).fill(NODAYS),nm=[];
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
    }).catch(function(){state='failed';}).then(function(){ctx.redraw(true);settle();});
  }
  // the hash holds only what differs from the defaults; a legacy link keeps its sort= and its tiers until a weight is touched (pri= values under 4 would read as the old levels, so they are written as 4)
  function hash(){
    var t=location.hash.slice(1).split('&').filter(function(x){return x&&!/^(sort|conf|gap|pri|base)=/.test(x);});
    if(st.top!==5)t.push('conf='+(st.top===100?'all':st.top));
    if(st.gap)t.push('gap='+st.gap[0]+'-'+st.gap[1]);
    if(st.legacy){if(st.sort)t.push('sort='+st.sort);}
    else t.push('pri='+(alloff()?'none':KEYS.filter(function(k){return st.w[k];}).map(function(k){return k+':'+Math.max(4,st.w[k]);}).join(',')));
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
    if(st.legacy){
      if(w.conf)s+=w.conf*ctx.conf(i,lv);
      if(w.gap&&tier)s+=w.gap*tier[i];
      if(lv===3&&(w.risk||w.inv)){var f=ctx.flag(i,!!w.inv);s+=w.risk*(f&1)+w.inv*(f>>1&1);}
      if(w.out&&ctx.hasOut())s+=w.out*ctx.out(i);
      return s;
    }
    if(w.conf)s+=w.conf*ctx.cont(i,lv);
    if(w.gap&&days&&days[i]!==NODAYS)s+=w.gap*(1-Math.min(days[i],LIT)/LIT);
    if(lv===3&&(w.risk||w.inv)){var g=ctx.flag(i,!!w.inv);s+=w.risk*(g&1)+w.inv*(g>>1&1);}
    if(w.out&&ctx.hasOut())s+=w.out*ctx.out(i);
    return s/100;
  }
  // the weighted rows by weight, then the others
  function summary(lv){
    var on=KEYS.filter(function(k){return disp(k)>0&&applies(k,lv);}).sort(function(a,b){return disp(b)-disp(a);}),base=BASES[st.base];
    if(!on.length)return base[0].toUpperCase()+base.slice(1);
    var t=on.map(function(k){return NAMES[k][1];}),r=t[0][0].toUpperCase()+t[0].slice(1)+' first'+t.slice(1).map(function(x){return ', then '+x;}).join('');
    return st.explicit?r+', then '+base:r;
  }
  // a row's name: a label for its input, or a toggletip trigger beside it (a term inside a label would not open on a click)
  function name(text,id,key,input){
    var n=el(key?'span':'label',null,text);
    if(key){n.dataset.explain=key;n.id=id+'-n';input.setAttribute('aria-labelledby',n.id);}else n.htmlFor=id;
    return n;
  }
  function slider(id,min,max,text,key){
    var r=el('div','prow2'),i=el('input'),b=el('b');
    i.type='range';i.id=id;i.min=min;i.max=max;i.step=1;r.append(name(text,id,key,i),b,i);
    return {row:r,input:i,out:b};
  }
  // the presets, the weights (one row each, with a bar), Then by, and the two filters, in #sorto; draw hides the rows a level has no data for
  function build(){
    var o=$('sorto');
    if(!o)return;
    var pre=el('div','ppre'),sum=el('p','psum'),box=el('div','prows'),chips={},rows={},sel={},bars={},outs={},ins={};
    sum.id='psum';sum.setAttribute('aria-live','polite');
    PRESETS.forEach(function(x){
      var b=el('button','qchip pchip',x[1]);b.type='button';b.dataset.preset=x[0];chips[x[0]]=b;
      b.onclick=function(){toNew();KEYS.forEach(function(k){st.w[k]=x[2][k]||0;});if(x[0]==='newest'){st.base='new';st.explicit=false;}change();};
      pre.appendChild(b);});
    KEYS.forEach(function(k){
      var r=el('div','pw'),i=el('input'),b=el('b'),mv=el('span','pmv'),u=el('button',null,'↑'),d=el('button',null,'↓'),bar=el('span','pbar'),f=el('i');
      i.id='pw-'+k;var l=name(NAMES[k][0],i.id,EXPLAIN[k],i);
      i.type='range';i.min=0;i.max=100;i.step=1;
      u.type=d.type='button';u.setAttribute('aria-label','Move '+NAMES[k][0]+' up');d.setAttribute('aria-label','Move '+NAMES[k][0]+' down');
      u.onclick=function(){move(k,-1);};d.onclick=function(){move(k,1);};
      i.oninput=function(){toNew();st.w[k]=+i.value;UI.hold=true;show();change(150);};
      i.onchange=function(){UI.hold=false;order();};
      mv.append(u,d);bar.appendChild(f);r.append(l,i,b,mv,bar);box.appendChild(r);
      rows[k]=r;ins[k]=i;outs[k]=b;bars[k]=f;});
    var bs=el('select'),br=el('div','prow2'),bl=el('label',null,'Then'),sh=el('button','lnk','Shuffle'),rs=el('button','lnk','Reset to defaults');
    bl.htmlFor=bs.id='pbase';sh.type=rs.type='button';rs.id='preset';
    [['new','newest'],['old','oldest'],['rand','random']].forEach(function(x){var op=el('option',null,x[1]);op.value=x[0];bs.appendChild(op);});
    bs.onchange=function(){st.base=bs.value;st.explicit=true;if(st.base==='rand')st.seed=1+Math.floor(Math.random()*1e6);change();};
    sh.onclick=function(){st.seed=1+Math.floor(Math.random()*1e6);change();};
    rs.onclick=function(){st=Object.assign(read(),{top:5,gap:null,w:Object.assign({},DEFAULT),legacy:true,sort:null,base:'new',explicit:false});change();};
    br.append(bl,bs,sh);
    var top=slider('ptop',1,100,'Best','best-match'),dual=el('div','prow2 pdl'),dl=el('span'),gv=el('b'),lo=el('input'),hi=el('input'),box2=el('div','pdual'),cap=el('div','pcap');
    top.input.oninput=function(){st.top=+top.input.value;change(150);};
    dl.textContent='Survey days';dl.dataset.explain='survey-days';
    [[lo,'pgl','Fewest survey days'],[hi,'pgh','Most survey days']].forEach(function(x){
      x[0].type='range';x[0].id=x[1];x[0].min=0;x[0].max=LIT0;x[0].step=1;x[0].setAttribute('aria-label',x[2]);
      x[0].oninput=function(){
        var a=+lo.value,b=+hi.value;if(x[0]===lo&&a>b)hi.value=a;if(x[0]===hi&&b<a)lo.value=b;
        a=+lo.value;b=+hi.value;st.gap=a===0&&b>=LIT0?null:[a,b];change(150);};});
    box2.append(lo,hi);cap.append(el('span',null,'none'),el('span',null,'enough'));dual.append(dl,gv,box2,cap);
    var fl=el('div','pgrp');fl.append(top.row,dual);
    var hr=el('hr');
    o.append(pre,sum,box,br,hr,fl);
    (UI={sum:sum,chips:chips,rows:rows,box:box,ins:ins,outs:outs,bars:bars,top:top,lo:lo,hi:hi,gv:gv,base:bs,shuffle:sh,reset:rs,hold:false});
    var ft=$('pfoot');if(ft)ft.prepend(rs);
  }
  function show(){KEYS.forEach(function(k){var v=disp(k);UI.ins[k].value=v;UI.outs[k].textContent=v?v+'%':'off';UI.bars[k].style.width=v+'%';
    UI.ins[k].setAttribute('aria-valuetext',NAMES[k][0]+' '+(v?v+'%':'off'));});}
  // the visible rows by weight, highest first; focus stays where it was
  function order(){
    var at=document.activeElement,l=KEYS.slice().sort(function(a,b){return disp(b)-disp(a)||KEYS.indexOf(a)-KEYS.indexOf(b);});
    l.forEach(function(k){UI.box.appendChild(UI.rows[k]);});
    if(at&&at!==document.activeElement&&at.isConnected)at.focus();
  }
  function vis(){return [].map.call(UI.box.children,function(r){return KEYS.filter(function(k){return UI.rows[k]===r;})[0];}).filter(function(k){return !UI.rows[k].hidden;});}
  // a row swaps weights with its neighbour; equal weights part by one
  function move(k,d){
    var l=vis(),j=l.indexOf(k)+d,o=l[j];
    if(!o)return;
    toNew();var a=st.w[k],b=st.w[o];
    if(a!==b){st.w[k]=b;st.w[o]=a;}
    else if(d<0){if(a<100)st.w[k]=a+1;else st.w[o]=a-1;}
    else if(a>0)st.w[k]=a-1;else st.w[o]=1;
    change();
  }
  build();
  load();
  return {
    ready:ready,  // settles once the checklist has loaded or failed and the redraw is done
    // a record the filters keep: level 3's Best x% and every level's survey days range
    pass:function(i,kind){
      if(kind===3&&st.top<100){var p=ctx.pct(i);if(p!=null&&p>st.top/100)return false;}
      if(!st.gap||state!=='ready')return true;
      var d=days[i];
      return d!==NODAYS&&d>=st.gap[0]&&(st.gap[1]>=LIT||d<=st.gap[1]);
    },
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
      var w=el('span','gapw'),b=el('button','gap',days[i]+'/'+names[i][1]+' days'),a=el('a','gapx','↗'),
        full='Survey days: '+days[i]+' of '+names[i][1]+' observer-days in this 25 km cell';
      b.type='button';b.dataset.explain='survey-days';b.title=full+'. Click to keep cells with '+days[i]+' or fewer';b.setAttribute('aria-label',full+'. Keep cells with '+days[i]+' or fewer');
      b.onclick=function(){st.gap=days[i]>=LIT?null:[0,days[i]];change();};
      a.href=BASE+'?at='+P.lonlat[2*i+1].toFixed(3)+','+P.lonlat[2*i].toFixed(3)+'&res='+RES+'&g='+encodeURIComponent(names[i][0])+'&goal=cl';
      a.target='_blank';a.rel='noopener';a.title=names[i][1]+' make a checklist (where-to-blitz)';a.setAttribute('aria-label','Open this cell in where-to-blitz');
      w.append(b,a);return w;
    },
    // a level 3 record's "Best 1%" badge: a click keeps that band
    confBadge:function(i,text){
      var b=el('button','conf',text),n=[1,5,25][ctx.band(i)];
      b.type='button';b.dataset.explain='best-match';b.title='Click to keep the Best '+n+'%';b.onclick=function(){st.top=n;change();};
      return b;
    },
    // the filters' names for the count line
    label:function(){return st.top<100?'Best '+st.top+'%':'';},
    gaplabel:function(){return st.gap&&state==='ready'?'survey days '+st.gap[0]+'-'+st.gap[1]:'';},
    // the controls and the summary line, for level lv
    draw:function(lv){
      if(!UI)return;
      var pr=preset(),btn=$('sortb');
      UI.top.row.hidden=!(lv===3&&ctx.hasRank());UI.top.input.value=st.top;UI.top.out.textContent=st.top+'%';
      var g=st.gap||[0,LIT0];
      UI.lo.value=g[0];UI.hi.value=g[1];UI.lo.style.zIndex=g[0]>LIT0/2?2:1;UI.gv.textContent=g[0]+'-'+g[1];
      UI.lo.setAttribute('aria-valuetext',g[0]+' survey days');UI.hi.setAttribute('aria-valuetext',g[1]+' survey days');
      KEYS.forEach(function(k){UI.rows[k].hidden=!applies(k,lv);});
      show();if(!UI.hold)order();
      PRESETS.forEach(function(x){UI.chips[x[0]].setAttribute('aria-pressed',String(pr===x[0]));});
      UI.base.value=st.base;UI.shuffle.hidden=st.base!=='rand';UI.reset.hidden=isdef();
      UI.sum.hidden=!!pr;
      UI.sum.textContent=summary(lv)+(state==='load'&&(st.w.gap||st.gap)?' (reading the where-to-blitz checklist…)':
        state==='failed'?'. The where-to-blitz checklist did not load, so gaps are ignored.':'');
      var nm=pr?PRESETS.filter(function(x){return x[0]===pr;})[0][1]:'Custom';
      btn.hidden=false;
      if(btn.dataset.name!==nm){btn.dataset.name=nm;document.dispatchEvent(new Event('change'));}  // the shell writes the button's label
    }
  };
};
F.compare=compare;
return F;
})();
