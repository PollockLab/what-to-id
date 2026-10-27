// What the map's record card adds to the photo, name and dates: the record's closest matches, as in the photo space
// (the atlas index at META.data_url; numbered thumbnails here, the same numbers on the map's dots) and its range chip
// (pool-levels-range.bin, through identify_ranges.js). Either is simply left out when its data is missing.
// MapCard(c), c {META, P() the records, TAXA(), NOTAX, nbr(ids) the dots, go(id) opens a record's card or says it is
// not on the map, place() puts the card back beside its point}.
var MapCard=(function(){
'use strict';
function el(tag,cls,text){var e=document.createElement(tag);if(cls)e.className=cls;if(text!=null)e.textContent=text;return e;}
return function(c){
  var DATA=c.META.data_url&&new URL(c.META.data_url,location.href).href.replace(/\/*$/,'/'),
    idx=null,R=null,RUN=0,CUR=-1,CACHE=new Map();
  function open(){return AtlasSearchIndex.open(DATA,{whole:4<<20});}
  async function neighbors(id){
    idx=idx||open();idx.catch(function(){idx=null;});  // a failed open is tried again next time
    try{return await (await idx).neighbors(id);}
    catch(e){  // the daily update renamed files: reload the manifest once
      if(!e.stale)throw e;
      idx=open();return (await idx).neighbors(id);
    }
  }
  function chip(){
    var box=document.getElementById('rng'),x=R&&box&&CUR>=0&&!box.firstChild&&R.chip(CUR,0);
    if(x)box.appendChild(x);
  }
  function list(id,hits){
    var rank={},ul=el('ul','nbrs'),box=document.getElementById('nbrs'),a=el('a',null,'More like this'),
      cards=AtlasSearchMeta.build(hits,CACHE).cards;
    hits.forEach(function(h,k){rank[h.id]=k+1;});
    cards.forEach(function(x){
      var label=x.common||x.name||'Unidentified',li=el('li'),b=el('button');
      b.type='button';b.dataset.id=x.id;b.title=label;b.setAttribute('aria-label','Match '+rank[x.id]+': '+label);
      if(x.photo){var im=el('img');im.src=x.photo;im.alt=label;im.loading='lazy';b.appendChild(im);}else b.textContent=label;
      b.onclick=function(){if(!c.go(x.id))window.open('https://www.inaturalist.org/observations/'+x.id,'_blank','noopener');};
      li.append(b,el('span','rank',rank[x.id]));ul.appendChild(li);
    });
    if(!cards.length||!box)return;
    a.href='search.html#id='+id;a.target='_blank';a.rel='noopener';
    var p=el('p','mt','Closest matches · ');p.appendChild(a);
    box.replaceChildren(p,ul);box.hidden=false;c.place();
  }
  return {
    // the card of record i is drawn: its chip now, its matches when they arrive
    show:function(i){
      var id=c.P().id[i],run=++RUN;
      CUR=i;if(R)R.close();chip();
      if(!DATA)return;
      neighbors(id).then(function(hits){
        if(run!==RUN||!hits||!hits.length)return;
        hits.sort(function(a,b){return b.score-a.score;});  // rank 1 is the highest cosine
        c.nbr(hits.map(function(h){return h.id;}));
        return AtlasSearchMeta.fetchObservations(hits.map(function(h){return h.id;}),function(u){return fetch(u);},CACHE)
          .then(function(){if(run===RUN)list(id,hits);});
      }).catch(function(){});  // no matches for this record, or none loaded: the section stays hidden
    },
    hide:function(){RUN++;CUR=-1;if(R)R.close();},
    // the range file has arrived, after every shard: a card already open gets its chip
    range:function(buf){
      var P=c.P();
      R=IdentifyRanges(buf,{P:{n:P.n,lonlat:P.pos},look:function(){return null;},redraw:function(){},
        name:function(i){var t=P.tax[i]!==c.NOTAX&&c.TAXA()[P.tax[i]];return t?t[0]:null;}});
      chip();
    }
  };
};
})();
