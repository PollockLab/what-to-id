// The map's filter state and the rules that turn it into values a GPU filter can read, apart from the
// page: the hash, the calendar lookups, each record's category values and the category lists. map.js
// runs it on the map's records; the photo space runs it on its own. TX (map_taxa.js) and CH
// (map_chips.js) are loaded before it.
function MapFilter(META){
'use strict';
var DAY=864e5,D0=Date.parse(META.day0+'T00:00:00Z'),NO=65535,NOTAX=65535,LAST=META.days-1;
var FLAG={introduced:1,threatened:2,obscured:4,imprecise:8,earlyObs:16,earlyUp:32},ONLYFLAG={introduced:'introduced',
  threatened:'threatened'},ONLYKEYS=Object.keys(ONLYFLAG);
// Each record's status value: bit 1 introduced, 2 threatened, 4 outside the chosen location accuracy
// (set by accOut, so it follows the choice and not the data), 8 kept by the taxon picks, the area and
// the projects and not deleted, 16 one record in ten.
var ST_INTRO=1,ST_THREAT=2,ST_INEXACT=4,ST_KEEP=8,ST_SAMPLE=16;
// The location accuracy choices, [key, label, hint]; the key is also the hash value of acc and, but for
// unknown and known, the metres. A record's accuracy class sits in its flags: 0 unknown, 1 over 1 km
// (bit 8), then within 1 km, 100 m and 10 m (bits 64, 128, 192), so each choice but unknown is a least
// class. Known and the precision choices also drop obscured records: the map draws those at rounded
// public coordinates, so their accuracy says nothing about the point drawn. Unknown keeps them.
var ACCDEF=[['unknown','Accuracy unknown','No accuracy reported for the location'],
  ['known','Accuracy known','Observer or device reported how accurate the location is. Hides obscured locations'],
  ['1000','Within 1 km','Reported accuracy of 1 km or better. Hides obscured locations'],
  ['100','Within 100 m','Reported accuracy of 100 m or better. Hides obscured locations'],
  ['10','Within 10 m','Reported accuracy of 10 m or better. Hides obscured locations']],
  ACCMIN={known:1,'1000':2,'100':3,'10':4},ACCKEYS=ACCDEF.map(function(a){return a[0];});
function accClass(f){var h=f>>6&3;return h?h+1:f>>3&1;}
// ST_INEXACT when a record with flags f fails the choice a ('' for any).
function accOut(a,f){return a&&(a==='unknown'?accClass(f)>0:accClass(f)<ACCMIN[a]||f&FLAG.obscured)?ST_INEXACT:0;}
function iso(d){return new Date(D0+d*DAY).toISOString().slice(0,10);}
function dayOf(s){var t=Date.parse(s+'T00:00:00Z');return isNaN(t)?null:Math.round((t-D0)/DAY);}
function clamp(d){return Math.max(0,Math.min(LAST,d));}
// Calendar lookups by day: month of year, day of month, weekday (Monday is 0) and month number
// counted from the first day's month, which indexes META.totals.
var MOY=new Uint8Array(META.days),DOM=new Uint8Array(META.days),DOW=new Uint8Array(META.days),
  MI=new Uint16Array(META.days),Y0=new Date(D0).getUTCFullYear(),M0=new Date(D0).getUTCMonth();
for(var d=0;d<META.days;d++){var t=new Date(D0+d*DAY);MOY[d]=t.getUTCMonth();DOM[d]=t.getUTCDate();
  DOW[d]=(t.getUTCDay()+6)%7;MI[d]=(t.getUTCFullYear()-Y0)*12+MOY[d]-M0;}

// The filter state out of a URLSearchParams. Groups and show only hold chip states (see
// map_chips.js): {Insecta:'inc', Aves:'not'}. area, park and bcpark stay as the hash wrote them.
function read(h){
  var S={up:h.get('by')==='uploaded',lo:0,hi:LAST,months:0},f=dayOf(h.get('from')||''),t=dayOf(h.get('to')||'');
  if(f!=null)S.lo=clamp(f);if(t!=null)S.hi=clamp(t);
  if(S.lo>S.hi){var sw=S.lo;S.lo=S.hi;S.hi=sw;}
  (h.get('months')||'').split(',').forEach(function(m){if(+m>=1&&+m<=12)S.months|=1<<(m-1);});
  S.groups=CH.read(h.get('groups'),META.groups);
  S.only=CH.read(h.get('only'),ONLYKEYS.filter(function(k){return META.flags.indexOf(ONLYFLAG[k])>=0;}));
  // an old link's only=exact was "within 1 km or unknown"; it now reads as within 1 km, which drops the unknown
  S.acc=META.flags.indexOf('accuracy')<0?'':ACCKEYS.indexOf(h.get('acc'))>=0?h.get('acc'):
    /(^|,)exact(,|$)/.test(h.get('only')||'')?'1000':'';
  S.picks=TX.read(h.get('taxa'));S.oldq=S.picks.length?'':h.get('q')||'';
  S.area=h.get('area')||'';S.park=h.get('park')||'';S.bcpark=h.get('bcpark')||'';
  return S;
}
// The hash parts for the dates, months, groups, show only and taxa; the area and projects write their own.
function write(S){
  var h=[];if(S.up)h.push('by=uploaded');
  if(S.lo>0)h.push('from='+iso(S.lo));if(S.hi<LAST)h.push('to='+iso(S.hi));
  if(S.months){var ms=[];for(var m=0;m<12;m++)if(S.months>>m&1)ms.push(m+1);h.push('months='+ms);}
  if(CH.any(S.groups))h.push('groups='+CH.write(S.groups,META.groups));
  if(CH.any(S.only))h.push('only='+CH.write(S.only,ONLYKEYS));
  if(S.acc)h.push('acc='+S.acc);
  if(S.picks.length)h.push('taxa='+TX.write(S.picks));
  return h;
}
// Record i's filter values into days (observed, uploaded; -1 for none) and cat (four bytes: group,
// observed month, uploaded month with 12 for no date, status), from its columns o, u and f (flags).
function record(days,cat,i,grp,o,u,f){
  days[2*i]=o===NO?-1:o;days[2*i+1]=u===NO?-1:u;
  cat[4*i]=grp;cat[4*i+1]=o===NO?12:MOY[o];cat[4*i+2]=u===NO?12:MOY[u];
  cat[4*i+3]=(f&FLAG.introduced?ST_INTRO:0)|(f&FLAG.threatened?ST_THREAT:0)|
    (i%10===0?ST_SAMPLE:0);
}
// The category lists the filter takes: groups, observed month, uploaded month and status values.
// inc: a taxon is included, so the groups are part of the kept bit (see CH.groupPass); thin: the
// one record in ten drawn while the view moves.
// The status bits the show only chips require and hide; the accuracy choice is always hidden.
function status(S){
  var req=0,hide=ST_INEXACT;
  [['introduced',ST_INTRO],['threatened',ST_THREAT]].forEach(function(o){var v=S.only[o[0]];
    if(v==='not')hide|=o[1];else if(v)req|=o[1];});
  return {req:req,hide:hide};
}
function categories(S,inc,thin){
  var groups=[],mon=[],all=[],st=[],s=status(S),req=s.req,hide=s.hide,i;
  CH.groupPass(S.groups,META.groups,inc).forEach(function(v,j){if(v)groups.push(j);});
  for(i=0;i<13;i++){all.push(i);if(S.months?i<12&&S.months>>i&1:true)mon.push(i);}
  for(i=0;i<2*ST_SAMPLE;i++)if(i&ST_KEEP&&(i&req)===req&&!(i&hide)&&(!thin||i&ST_SAMPLE))st.push(i);
  return [groups,S.up?all:mon,S.up?mon:all,st];
}
// With a taxon included the picked groups join the taxa as one set (see CH.groupPass): per group
// index whether it is picked, or null with no taxon included or no group picked.
function groupSet(S,TF){return TF.inc&&CH.picked(S.groups,META.groups,'inc').length?
  META.groups.map(function(g){return S.groups[g]==='inc';}):null;}
// Into out, 1 per record the taxon picks keep and 0 per record they leave out. TF is TX.filter's
// result and gs the groupSet; tax and grp are the records' columns.
function keep(TF,gs,tax,grp,n,out){
  var ti=TF.inc,te=TF.exc;
  for(var i=0;i<n;i++){var t=tax[i],k=!ti||(t!==NOTAX&&ti[t]===1)||(gs!==null&&gs[grp[i]]);
    if(te&&t!==NOTAX&&te[t]===1)k=false;out[i]=k?1:0;}
  return out;
}
// Clears from out each record the dates, months and show only chips leave out, as the map's filter does:
// the dates and months read the observed day, or the uploaded one with by=uploaded, and a record with no
// date fails any date or month limit. o, u and f are the records' observed day, uploaded day and flags.
function rest(S,o,u,f,n,out){
  var day=S.up?u:o,full=S.lo===0&&S.hi===LAST,m=S.months,s=status(S),req=s.req,hide=s.hide,
    fi=FLAG.introduced,ft=FLAG.threatened;
  for(var i=0;i<n;i++){
    if(!out[i])continue;
    var d=day[i],b=(f[i]&fi?ST_INTRO:0)|(f[i]&ft?ST_THREAT:0)|accOut(S.acc,f[i]);
    if((!full&&(d===NO||d<S.lo||d>S.hi))||(m&&(d===NO||!(m>>MOY[d]&1)))||(b&req)!==req||b&hide)out[i]=0;
  }
  return out;
}
var MONTH=['January','February','March','April','May','June','July','August','September','October','November',
  'December'];
// The show only chips as [key, label, flag, hint], those the data has the flag for.
var ONLYDEF=[['introduced','Introduced to BC','introduced','Species not native to BC'],
  ['threatened','Threatened','threatened','Species with a threatened status']]
  .filter(function(o){return META.flags.indexOf(o[2])>=0;});
return {rest:rest,ACCDEF:ACCDEF,accClass:accClass,accOut:accOut,MONTH:MONTH,ONLYDEF:ONLYDEF,DAY:DAY,D0:D0,NO:NO,NOTAX:NOTAX,LAST:LAST,FLAG:FLAG,ONLYFLAG:ONLYFLAG,ONLYKEYS:ONLYKEYS,ST_INTRO:ST_INTRO,
  ST_THREAT:ST_THREAT,ST_INEXACT:ST_INEXACT,ST_KEEP:ST_KEEP,ST_SAMPLE:ST_SAMPLE,iso:iso,dayOf:dayOf,clamp:clamp,
  MOY:MOY,DOM:DOM,DOW:DOW,MI:MI,M0:M0,read:read,write:write,record:record,categories:categories,groupSet:groupSet,keep:keep};
}
// One colour per life group, by index in META.groups, shared by the map and the photo space: 16 distinct
// hues, each at least 2:1 against both the light and the dark page.
MapFilter.PAL=[[0,114,178],[213,94,0],[0,158,115],[190,160,0],[204,121,167],[86,180,233],[230,70,70],[120,60,170],[110,110,110],[160,60,40],[150,130,200],[40,120,60],[140,200,50],[70,90,220],[255,140,100],[0,190,190]];
// The hash tokens a selection is made of, as one string.
MapFilter.tokens=function(hash){return hash.replace(/^#/,'').split('&').filter(function(t){
  return /^(by|from|to|months|groups|only|acc|taxa)=/.test(t);}).join('&');};
// Live selection sync for a page inside the split view. key() is the selection the page holds, apply(str) puts
// one in place. A change goes to the parent at most once a frame; one that comes from outside (the parent's
// message, a hash change) is applied and not sent back.
MapFilter.sync=function(o){
  var last=null,raf=0;
  function send(){
    if(parent===window||raf)return;
    raf=requestAnimationFrame(function(){raf=0;var k=o.key();
      if(k!==last){last=k;parent.postMessage({type:'wtid-selection',sel:k},location.origin);}});
  }
  function take(str){if(str!==o.key())o.apply(str);last=str;}
  // a slow apply (a brush dragged over 3M points) must not queue: only the latest message is applied, once a frame
  var pend=null;
  addEventListener('message',function(e){
    if(e.origin===location.origin&&e.source===parent&&e.data&&e.data.type==='wtid-selection'&&
      typeof e.data.sel==='string'){
      if(pend===null)requestAnimationFrame(function(){var s=pend;pend=null;take(s);});
      pend=e.data.sel;}});
  addEventListener('hashchange',function(){take(MapFilter.tokens(location.hash));});
  return {send:send};
};
