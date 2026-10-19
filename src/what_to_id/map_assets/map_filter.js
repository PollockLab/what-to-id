// The map's filter state and the rules that turn it into values a GPU filter can read, apart from the
// page: the hash, the calendar lookups, each record's category values and the category lists. map.js
// runs it on the map's records; the photo space runs it on its own. TX (map_taxa.js) and CH
// (map_chips.js) are loaded before it.
function MapFilter(META){
'use strict';
var DAY=864e5,D0=Date.parse(META.day0+'T00:00:00Z'),NO=65535,NOTAX=65535,LAST=META.days-1;
var FLAG={introduced:1,threatened:2,obscured:4,imprecise:8,earlyObs:16,earlyUp:32},ONLYFLAG={introduced:'introduced',
  threatened:'threatened',exact:'obscured'},ONLYKEYS=Object.keys(ONLYFLAG);
// Each record's status value: bit 1 introduced, 2 threatened, 4 obscured or imprecise, 8 kept by the
// taxon picks, the area and the projects and not deleted, 16 one record in ten.
var ST_INTRO=1,ST_THREAT=2,ST_INEXACT=4,ST_KEEP=8,ST_SAMPLE=16;
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
  S.only=CH.read(h.get('only'),ONLYKEYS.filter(function(k){return META.flags.indexOf(ONLYFLAG[k])>=0;}),['exact']);
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
  if(S.picks.length)h.push('taxa='+TX.write(S.picks));
  return h;
}
// Record i's filter values into days (observed, uploaded; -1 for none) and cat (four bytes: group,
// observed month, uploaded month with 12 for no date, status), from its columns o, u and f (flags).
function record(days,cat,i,grp,o,u,f){
  days[2*i]=o===NO?-1:o;days[2*i+1]=u===NO?-1:u;
  cat[4*i]=grp;cat[4*i+1]=o===NO?12:MOY[o];cat[4*i+2]=u===NO?12:MOY[u];
  cat[4*i+3]=(f&FLAG.introduced?ST_INTRO:0)|(f&FLAG.threatened?ST_THREAT:0)|
    (f&(FLAG.obscured|FLAG.imprecise)?ST_INEXACT:0)|(i%10===0?ST_SAMPLE:0);
}
// The category lists the filter takes: groups, observed month, uploaded month and status values.
// inc: a taxon is included, so the groups are part of the kept bit (see CH.groupPass); thin: the
// one record in ten drawn while the view moves.
function categories(S,inc,thin){
  var groups=[],mon=[],all=[],st=[],req=0,hide=0,i;
  CH.groupPass(S.groups,META.groups,inc).forEach(function(v,j){if(v)groups.push(j);});
  for(i=0;i<13;i++){all.push(i);if(S.months?i<12&&S.months>>i&1:true)mon.push(i);}
  [['introduced',ST_INTRO],['threatened',ST_THREAT],['exact',ST_INEXACT]].forEach(function(o){var v=S.only[o[0]];
    if(v==='not'||v&&o[0]==='exact')hide|=o[1];else if(v)req|=o[1];});
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
return {DAY:DAY,D0:D0,NO:NO,NOTAX:NOTAX,LAST:LAST,FLAG:FLAG,ONLYFLAG:ONLYFLAG,ONLYKEYS:ONLYKEYS,ST_INTRO:ST_INTRO,
  ST_THREAT:ST_THREAT,ST_INEXACT:ST_INEXACT,ST_KEEP:ST_KEEP,ST_SAMPLE:ST_SAMPLE,iso:iso,dayOf:dayOf,clamp:clamp,
  MOY:MOY,DOM:DOM,DOW:DOW,MI:MI,M0:M0,read:read,write:write,record:record,categories:categories,groupSet:groupSet,keep:keep};
}
