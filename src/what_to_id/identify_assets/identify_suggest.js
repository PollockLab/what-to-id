// One-tap suggestions at the top of each What, When, Where and Who panel on Identify, above the full filters. Each applies
// filters that already exist (the same address keys), so a suggestion can be undone with the filter it set. Hidden in Batches.
// IdentifySuggest(o), o {S, META, mf, nf, P(), taxa(), allc() (records per group), short(g), tm (MapTime), changed(), rewrite(drop, add),
// area(rings, hash, label) (the area changed, the map reloads), get(url), embedded}. Returns update(), after every change.
// where() starts the park list's fetch, called when Where opens. Needs group_icons.js, map_area.js (the park list's address and MapArea.encode) and the panels' #sgwhat, #sgwhen, #sgwhere, #sgwho.
var IdentifySuggest=(function(){
'use strict';
// Every English string, in one place for the translation file to take over; {n} and {d} are filled in.
var T={
  what:'Suggested',recent:'Recently used',recentSub:'Recently used',backlog:'Biggest backlogs',backlogSub:'{n} records waiting',
  blitz:'Blitz targets',blitzSub:'{n} threatened or introduced',lists:'Suggestions',
  when:'Quick picks',visit:'Since your last visit',visitSub:'From {d}',allSub:'Every record',rangeSub:'{a} to {b}',
  where:'Near you',near:'Near me',nearSub:'Within 50 km of where you are',nearWait:'Finding where you are…',
  denied:'Location is blocked for this site. Allow it in the browser, or draw an area below.',
  unavailable:'Your location is not available. Draw an area below instead.',outside:'You seem to be outside this map’s area.',
  places:'Suggested places',placesSub:'Up to {n} records waiting',placesLoad:'Loading parks…',placesFail:'The park list did not load.',
  who:'Your progress',opened:'{n} opened today',improving:'{n} of 10 improving IDs in 30 days',none:'Nothing opened yet today.',
  mine:'Not yet by me',mineSub:'Leave out what you identified',mineNeed:'Type your iNaturalist login below first.',
  mineExcl:'Untick “my observations” below first.',nobody:'Nobody has looked',nobodySub:'No one but the observer has identified it',
  second:'Needs a second opinion',secondSub:'One ID, and nobody agrees yet'
};
var NS='http://www.w3.org/2000/svg',R=50,PTS=64,KM=111.195,STORE={recent:'wtid-recent',visit:'wtid-lastvisit',opened:'wtid-opened',improving:'wtid-improving'},
  ICON={
    near:'<circle cx="12" cy="12" r="3"/><path d="M12 2v4M12 18v4M2 12h4M18 12h4"/>',
    park:'<path d="M12 21v-6M12 3l5 7h-3l4 6H6l4-6H7z"/>',clock:'<circle cx="12" cy="12" r="9"/><path d="M12 7v5l3 2"/>',
    cal:'<rect x="4" y="5" width="16" height="15" rx="2"/><path d="M4 10h16M9 3v4M15 3v4"/>',
    eye:'<path d="M2 12s4-7 10-7 10 7 10 7-4 7-10 7S2 12 2 12z"/><circle cx="12" cy="12" r="3"/>',
    two:'<circle cx="9" cy="9" r="3"/><circle cx="16" cy="10" r="2.4"/><path d="M3 19c0-3 3-5 6-5s6 2 6 5M16 14c3 0 5 2 5 5"/>',
    user:'<circle cx="12" cy="8" r="3.5"/><path d="M5 20c0-4 3-6 7-6s7 2 7 6"/>',leaf:'<path d="M5 19c0-9 5-14 14-14 0 9-5 14-14 14zM5 19l7-7"/>',
    warn:'<path d="M12 3l10 18H2zM12 10v5M12 18v.5"/>'
  };
function fmt(s,v){return s.replace(/\{(\w+)\}/g,function(m,k){return v[k]!=null?v[k]:m;});}
function el(tag,cls,text){var e=document.createElement(tag);if(cls)e.className=cls;if(text!=null)e.textContent=text;return e;}
function get(k,s){try{return JSON.parse((s?sessionStorage:localStorage).getItem(k));}catch(e){return null;}}
function put(k,v,s){try{(s?sessionStorage:localStorage).setItem(k,JSON.stringify(v));}catch(e){}}
function svg(inner,fill){var v=document.createElementNS(NS,'svg');v.setAttribute('viewBox',fill?'0 0 512 512':'0 0 24 24');v.setAttribute('aria-hidden','true');
  v.innerHTML=inner;return v;}
// the 50 km circle round a point as one ring of flat [lon, lat, ...]
function circle(lon,lat){
  var dl=R/KM,dn=dl/Math.cos(lat*Math.PI/180),r=[],i,a;
  for(i=0;i<PTS;i++){a=2*Math.PI*i/PTS;r.push(lon+dn*Math.cos(a),lat+dl*Math.sin(a));}
  return r;
}
return function(o){
var S=o.S,META=o.META,MF=o.mf,G=META.groups,box={},bt=function(){return document.body.classList.contains('bt');},
  rows={what:[],when:[],where:[],who:[]},msg={where:'',who:''},PN=null,PS=0,BLZ=null,seen=null,prev=null,LV=null;
['what','when','where','who'].forEach(function(k){box[k]=document.getElementById('sg'+k);});
var hasFlags=META.flags.indexOf('threatened')>=0||META.flags.indexOf('introduced')>=0;

// Recently used: the last groups and taxa picked, newest first, kept on this device
function recent(){var r=get(STORE.recent);return Array.isArray(r)?r:[];}
function note(){
  var inc=Object.keys(S.groups).filter(function(g){return S.groups[g]==='inc';}),ids=S.picks.filter(function(p){return !p.not;}).map(function(p){return p.id;}),
    now=inc.map(function(g){return 'g:'+g;}).concat(ids.map(function(i){return 't:'+i;}));
  if(seen){
    var fresh=now.filter(function(k){return seen.indexOf(k)<0;});
    if(fresh.length){
      var r=recent().filter(function(x){return fresh.indexOf(x.g?'g:'+x.g:'t:'+x.t)<0;});
      fresh.forEach(function(k){r.unshift(k[0]==='g'?{g:k.slice(2)}:{t:+k.slice(2)});});
      put(STORE.recent,r.slice(0,10));
    }
  }
  seen=now;
}
function groupOn(g){return S.groups[g]==='inc'&&Object.keys(S.groups).length===1;}
function pickGroup(g){var on=groupOn(g);S.groups={};if(!on)S.groups[g]='inc';o.changed();}
function pickTaxon(id){var on=S.picks.length===1&&S.picks[0].id===id&&!S.picks[0].not;S.picks=on?[]:[{id:id,not:false}];o.changed();}
function blitz(){
  if(BLZ||!hasFlags)return BLZ;
  var P=o.P(),c=new Uint32Array(G.length),i;
  if(!P.flags)return null;
  for(i=0;i<P.n;i++)if(P.flags[i]&3)c[P.grp[i]]++;
  return (BLZ=c);
}
function top(c,n){
  return G.map(function(g,k){return k;}).filter(function(k){return c[k]>0&&!/^(Animalia|Unknown)$/.test(G[k]);})
    .sort(function(a,b){return c[b]-c[a]||a-b;}).slice(0,n);
}
function grow(k,pre,c,sub){return {k:pre+G[k],g:G[k],j:k,t:o.short(G[k]),s:fmt(sub,{n:o.nf.format(c[k])}),on:groupOn(G[k]),fn:function(){pickGroup(G[k]);}};}
function whatRows(){
  var out=[],P=o.P(),ac=o.allc(),b=blitz(),tx=o.taxa();
  var rc=recent().slice(0,3).map(function(x){
    if(x.g)return G.indexOf(x.g)<0?null:{k:'r:g'+x.g,g:x.g,j:G.indexOf(x.g),t:o.short(x.g),s:T.recentSub,on:groupOn(x.g),fn:function(){pickGroup(x.g);}};
    var r=tx.filter(function(t){return t[2]===x.t;})[0];
    return r?{k:'r:t'+x.t,i:'leaf',t:r[1]||r[0],s:T.recentSub+(r[1]?' · '+r[0]:''),on:S.picks.length===1&&S.picks[0].id===x.t,fn:function(){pickTaxon(x.t);}}:null;
  }).filter(Boolean);
  if(rc.length)out.push({h:T.recent,rows:rc});
  if(ac&&P.n)out.push({h:T.backlog,rows:top(ac,3).map(function(k){return grow(k,'b:',ac,T.backlogSub);})});
  if(b&&top(b,1).length)out.push({h:T.blitz,rows:top(b,3).map(function(k){return grow(k,'z:',b,T.blitzSub);})});
  return out;
}

// When: the presets (the existing buttons do the work) and the days since the last visit
function visit(){
  var l=get(STORE.visit),d=new Date().toLocaleDateString('en-CA');
  if(prev===null){
    var s=get('wtid-prevvisit',true);
    prev=typeof s==='string'?s:typeof l==='string'?l:'';put('wtid-prevvisit',prev,true);
  }
  put(STORE.visit,d);
}
function whenRows(){
  var r=o.tm.presets.map(function(p){
    var b=p.range(),all=b[0]===0;
    return {k:'w:'+p.el.textContent,i:all?'cal':'clock',t:p.el.textContent,s:all?T.allSub:fmt(T.rangeSub,{a:MF.iso(b[0]),b:MF.iso(b[1])}),
      on:b[0]===S.lo&&b[1]===S.hi,fn:function(){p.el.click();}};
  }).filter(function(x){return !/12 months/.test(x.t);});
  var d=prev?MF.dayOf(prev):null;
  if(d!=null&&d<=MF.LAST)r.unshift({k:'w:visit',i:'eye',t:T.visit,s:fmt(T.visitSub,{d:prev}),on:S.lo===MF.clamp(d)&&S.hi===MF.LAST,
    fn:function(){S.lo=MF.clamp(d);S.hi=MF.LAST;o.changed();}});
  return [{h:T.when,rows:r}];
}

// Where: Near me on tap, and the parks with the most records waiting. A park's boundary comes from the map, which reloads.
function near(){
  if(bt())return;
  var g=navigator.geolocation;
  if(!g){msg.where=T.unavailable;return draw();}
  msg.where=T.nearWait;draw();
  g.getCurrentPosition(function(p){
    var lon=p.coords.longitude,lat=p.coords.latitude,b=META.bbox,m=0.45;
    if(b&&(lon<b[0]-m||lon>b[2]+m||lat<b[1]-m||lat>b[3]+m)){msg.where=T.outside;return draw();}
    var e=MapArea.encode([circle(lon,lat)]);msg.where='';o.area(e,'area='+e,'Near me');draw();
  },function(e){msg.where=e&&e.code===1?T.denied:T.unavailable;draw();},{timeout:12000,maximumAge:60000});
}
function parks(){
  if(PS||o.embedded)return;
  PS=1;
  o.get(META.parks).then(function(buf){
    var j=JSON.parse(new TextDecoder().decode(buf)),P=o.P(),i,c={},cell={},n=P.n;
    // shortcut: a record counts for every park whose box holds it, an upper bound (most parks have no polygon in the list); upgrade by testing polygons
    var list=j.parks.filter(function(r){return r[0].indexOf('-')<0&&r[4];});
    list.forEach(function(r){var b=r[4],x,y;
      for(x=Math.floor(b[0]*4);x<=Math.floor(b[2]*4);x++)for(y=Math.floor(b[1]*4);y<=Math.floor(b[3]*4);y++)(cell[x+','+y]=cell[x+','+y]||[]).push(r);});
    for(i=0;i<n;i++){
      var lo=P.lonlat[2*i],la=P.lonlat[2*i+1],cs=cell[Math.floor(lo*4)+','+Math.floor(la*4)]||[];
      cs.forEach(function(r){var b=r[4];if(lo>=b[0]&&lo<=b[2]&&la>=b[1]&&la<=b[3])c[r[0]]=(c[r[0]]||0)+1;});
    }
    PN=list.filter(function(r){return c[r[0]]>0;}).sort(function(a,b){return c[b[0]]-c[a[0]]||(a[1]<b[1]?-1:1);}).slice(0,5)
      .map(function(r){return {key:r[0],name:r[1],n:c[r[0]]};});
    PS=2;draw();
  }).catch(function(){PS=3;draw();});
}
function whereRows(){
  var h=location.hash,k=/(?:^|&)bcpark=([^&]*)/.exec(h),out=[{h:T.where,rows:[{k:'n:near',i:'near',t:T.near,s:T.nearSub,on:false,fn:near}]}];
  if(PN&&PN.length)out.push({h:T.places,rows:PN.map(function(p){
    return {k:'p:'+p.key,i:'park',t:p.name,s:fmt(T.placesSub,{n:o.nf.format(p.n)}),on:!!k&&decodeURIComponent(k[1])===p.key,
      fn:function(){o.area('','bcpark='+encodeURIComponent(p.key),p.name);}};})});
  return out;
}

// Who: the progress so far, then the three chips
function look(){var m=/(?:^|&)look=(nobody|second)(?:&|$)/.exec(location.hash.slice(1));return m&&m[1];}
function setLook(v){
  o.rewrite(function(x){return /^look=/.test(x);},look()===v?[]:['look='+v]);o.changed();
}
function mine(){
  var c=document.getElementById('usrunid'),on=/(^|,)unid(,|$)/.test(S.umode||''),why=!S.user?T.mineNeed:/(^|,)observer(,|$)/.test(S.umode||'')?T.mineExcl:'';
  return {k:'y:mine',i:'user',t:T.mine,s:T.mineSub,on:on,dis:!on&&(!!why||!c),why:why,fn:function(){if(c)c.click();}};
}
function progress(){
  var o1=get(STORE.opened),d=new Date().toLocaleDateString('en-CA'),im=get(STORE.improving),a=[];
  a.push(o1&&o1.d===d&&o1.ids&&o1.ids.length?fmt(T.opened,{n:o1.ids.length}):T.none);
  if(im&&typeof im.n==='number'&&im.d===d)a.push(fmt(T.improving,{n:im.n}));
  return a.join(' · ');
}
function whoRows(){
  var r=[mine()];
  if(!o.embedded)r.push({k:'y:nobody',i:'eye',t:T.nobody,s:T.nobodySub,on:look()==='nobody',fn:function(){setLook('nobody');}},
    {k:'y:second',i:'two',t:T.second,s:T.secondSub,on:look()==='second',fn:function(){setLook('second');}});
  return [{h:T.who,line:progress(),rows:r}];
}

// Drawing: the rows are rebuilt and the focused one found again by its key
function row(r){
  var li=el('li'),b=el('button','sgr'),t=el('span','sgi'),x=el('span','sgx'),s=el('span','sgs',r.s);
  b.type='button';b.dataset.k=r.k;
  if(r.g){t.appendChild(svg('<path d="'+(GROUP_ICONS[r.g]||GROUP_ICONS.Unknown)+'" transform="translate(0 480) scale(1 -1)"/>',true));
    t.style.setProperty('--c','rgb('+MapFilter.color(r.g,r.j).join(',')+')');t.classList.add('grp');}
  else t.appendChild(svg(ICON[r.i||'leaf']));
  x.append(el('span','sgt2',r.t),s);b.append(t,x);
  if(r.on!=null)b.setAttribute('aria-pressed',String(!!r.on));
  if(r.dis){b.setAttribute('aria-disabled','true');b.title=r.why;
    var hint=el('span','vh',' '+r.why);x.appendChild(hint);b.onclick=function(){msg.who=r.why;draw();};}
  else b.onclick=function(){if(!bt())r.fn();};
  li.appendChild(b);return li;
}
function section(secs,k){
  var b=box[k],f=document.activeElement,fk=f&&b.contains(f)?f.dataset.k:null,id;
  b.textContent='';
  secs.forEach(function(s,j){
    var u=el('ul','sgl'),head=el('p','sgh',s.h);
    id='sgh-'+k+j;head.id=id;u.setAttribute('aria-labelledby',id);u.setAttribute('role','list');
    s.rows.forEach(function(r){u.appendChild(row(r));});
    b.append(head);if(s.line)b.append(el('p','sgn muted',s.line));b.append(u);
  });
  if(msg[k]){var m=el('p','sgm',msg[k]);m.setAttribute('role','status');b.append(m);}
  else if(k==='where'){var q=el('p','sgm muted',PS===3?T.placesFail:PS!==1?'':T.placesLoad);q.setAttribute('role','status');b.append(q);}
  if(fk){var n=b.querySelector('[data-k="'+fk.replace(/"/g,'\\"')+'"]');if(n)n.focus();}
}
function draw(){
  if(!o.P().n)return;
  section(whatRows(),'what');section(whenRows(),'when');section(whereRows(),'where');section(whoRows(),'who');
}
function update(){
  if(!o.P().n)return;
  if(LV===null){visit();LV=true;}
  msg.who='';note();draw();
}
return {update:update,where:parks};
};
})();
