// Reference photos on the cards that name a look-alike: the label's and the look-alike's iNaturalist default photo side by
// side under the record's photo, so the call is made against examples rather than a name alone.
// IdentifyCompare(ctx), ctx {taxa (the TAXA table), tax (each record's taxa row), look(i), why(i) (level 3's runner-up
// [name, margin], or null), obs(id) (the observation, once fetched), more()}. fill(lis) adds them to the cards just drawn, 30 taxa to a request. Each photo links to its taxon page
// on iNaturalist and names its photographer and licence on hover, as the licences ask. Needs map_user.js (inatGate).
// open(li) shows the side panel: the observation's photos large and zoomable on the left, on the right the species the card
// names and its look-alikes (the model's runner-up, iNaturalist's similar species) each with a row of reference photos and a
// small range map (identify_refs.js), as in iNaturalist's Compare. Up and down pick the species, left and right step its photos
// (with Shift the record's), z zooms; j, k, Enter, c, s, u (undo) and Esc work through the cards without a tab.
// ctx.range() is the IdentifyRanges once loaded, else null. Strings: identify_compare_text.js. Needs identify_zoom.js, identify_refs.js.
var IdentifyCompare=(function(){
'use strict';
var AHEAD=3,MAX=30,ROWS=4,NOTAX=65535,PLACE=7085,TAXON='https://www.inaturalist.org/taxa/',TXT=IdentifyText;  // AHEAD: cards whose references load while the user is in iNat
function el(tag,cls,text){var e=document.createElement(tag);if(cls)e.className=cls;if(text!=null)e.textContent=text;return e;}
function size(u,s){return String(u).replace(/\/(square|small|medium)\./,'/'+s+'.');}
return function(ctx){
  var T=ctx.taxa,row=new Map(),photo=new Map(),full=new Map(),api=inatGate({gap:1000}),now=inatGate({gap:1000}),box=null,cur=null;
  T.forEach(function(t,r){row.set(t[0],r);});
  // [label taxa row, look-alike taxa row] for a card that names a look-alike in the taxa table, else null
  function pair(i){
    var l=ctx.look(i),a=ctx.tax[i],b=l==null?undefined:row.get(l);
    return a!==NOTAX&&a<T.length&&b!==undefined?[a,b]:null;
  }
  function fig(r,cap){
    var f=el('figure'),a=el('a'),img=el('img');
    a.href=TAXON+T[r][2];IdentifyFlow.link(a);
    img.loading='lazy';img.alt=cap+' '+T[r][0]+', reference photo';img.dataset.t=T[r][2];
    img.onerror=function(){img.removeAttribute('src');};
    a.append(img);f.append(a,el('figcaption',null,cap));f.title=T[r][0];show(img);
    return f;
  }
  // the photo once known: {url, by} with by iNaturalist's attribution line, or null for none
  function show(img){
    var p=photo.get(+img.dataset.t),f=img.closest('figure');if(p===undefined||img.src)return;
    if(p){img.src=p.url;if(p.by)f.title+='. Photo '+p.by;}else f.title+=' (no reference photo)';
  }
  // the taxa not yet known, 30 to a request; full keeps each whole record for the panel, whose own gate (q) skips the cards' queue
  // a taxon already asked for waits on that request, so a redraw does not queue it again; the panel (q) asks on its own
  var pend=new Map();
  function taxa(ids,q){
    var want=ids.filter(function(id,k){return !photo.has(id)&&(q||!pend.has(id))&&ids.indexOf(id)===k;});
    for(var k=0;k<want.length;k+=MAX){var part=want.slice(k,k+MAX),ask=(q||api)('taxa/'+part.join(',')+'?preferred_place_id='+PLACE).then(function(j){
      (j.results||[]).forEach(function(t){var d=t.default_photo;full.set(t.id,t);
        photo.set(t.id,d&&d.square_url?{url:size(d.square_url,'small'),by:d.attribution||''}:null);});}).catch(function(){});
      part.forEach(function(id){pend.set(id,ask);});}
    return Promise.all(ids.map(function(id){return pend.get(id);})).then(function(){
      ids.forEach(function(id){if(!photo.has(id))photo.set(id,null);pend.delete(id);});});
  }
  // the boxes go in at once, their size fixed, so the photos landing later do not move the card; the cards on screen ask first
  function fill(lis){
    var want=[],imgs=[],h=innerHeight;
    function off(li){var r=li.getBoundingClientRect();return r.bottom<0||r.top>h?1:0;}
    lis.slice().sort(function(a,b){return off(a)-off(b);}).forEach(function(li){var pr=pair(+li.dataset.i);if(!pr)return;
      var old=li.querySelector('.cmp'),b=el('div','cmp');
      b.append(fig(pr[0],TXT.role.label),fig(pr[1],li.dataset.lv==='3'?TXT.role.suggested:TXT.role.lookalike));  // level 3: the species to propose
      if(old)old.replaceWith(b);else (li.querySelector('.car')||li.querySelector('.title')).appendChild(b);
      imgs.push.apply(imgs,b.querySelectorAll('img'));
      pr.forEach(function(r){want.push(T[r][2]);});});
    return taxa(want).then(function(){imgs.forEach(show);});
  }

  // The panel. A card's species: the one it names (level 3's suggestion, a look-alike), else its label.
  function cards(){return [].slice.call(document.querySelectorAll('#grid .card,#sgrid .card'));}
  // a look-alike the taxa table lacks keeps its name, with no taxon id (0) for photos
  function named(li){
    if(!li.dataset.i)return null;
    var i=+li.dataset.i,l=ctx.look(i),pr=pair(i);
    return pr?T[pr[1]]:l!=null?[l,'',0]:ctx.tax[i]!==NOTAX?T[ctx.tax[i]]:null;
  }
  function build(){
    box=el('aside');box.id='cpanel';box.setAttribute('role','dialog');box.setAttribute('aria-labelledby','cphead');box.tabIndex=-1;box.hidden=true;
    box.innerHTML='<div class="cptop"><h2 id="cphead"></h2><span id="cpat" class="muted"></span>'+
      '<button type="button" id="cpx" class="arrow" aria-label="Close (Esc)">×</button></div>'+
      '<p id="cplive" aria-live="polite" style="position:absolute;width:1px;height:1px;overflow:hidden;clip-path:inset(50%)"></p>'+
      '<div class="cpbody"><div class="cpl"><div id="cpobs"></div><div id="cpdet"></div></div>'+
      '<div class="cpr"><p id="cpkeys" class="muted"></p><div id="cpwhy"></div><div id="cprefs"></div></div></div>'+
      '<div class="cpbar"><button type="button" id="cpk" class="arrow" aria-label="Previous card (k)" aria-keyshortcuts="k">‹</button>'+
      '<button type="button" id="cpj" class="arrow" aria-label="Next card (j)" aria-keyshortcuts="j">›</button>'+
      '<button type="button" id="cps" class="more" aria-keyshortcuts="s" title="Skip (s)">Skip</button>'+
      '<span id="cpc"></span><span id="cpt" class="muted" role="status"></span><button type="button" id="cpo" class="btn" aria-keyshortcuts="Enter" title="Identify on iNaturalist (Enter)">Identify (Enter)</button></div>';
    document.body.appendChild(box);
    if(matchMedia('(pointer: coarse)').matches){box.querySelector('#cpo').textContent='Identify';box.querySelector('#cpkeys').hidden=true;}  // no Enter key on touch
    else box.querySelector('#cpkeys').textContent=TXT.keys;
    box.querySelector('#cprefs').addEventListener('click',function(e){var c=e.target.closest('.cpref');if(c)pick_(rows.indexOf(c));});
    var redraw=function(){if(box&&!box.hidden)RF.repaint();};  // the maps read the theme's colours when drawn
    matchMedia('(prefers-color-scheme:dark)').addEventListener('change',redraw);
    new MutationObserver(redraw).observe(document.documentElement,{attributes:true,attributeFilter:['data-theme']});
    box.querySelector('#cpx').onclick=close;
    box.querySelector('#cpk').onclick=function(){go(-1);};box.querySelector('#cpj').onclick=function(){go(1);};
    box.querySelector('#cps').onclick=function(){IdentifyFlow.mark(cur,'Skipped');go(1);var l=box.querySelector('#cplive');if(!box.hidden)l.textContent='Skipped. '+l.textContent;};
    box.querySelector('#cpo').onclick=function(){
      var a=cur.querySelector('a.btn'),t=named(cur),m=box.querySelector('#cpt'),c=navigator.clipboard;if(!a)return;
      if(t&&c&&c.writeText)c.writeText(t[0]).then(function(){m.textContent='Copied '+t[0]+', paste in iNat';clearTimeout(m.t);
        m.t=setTimeout(function(){m.textContent='';},4000);},function(){});
      a.click();IdentifyFlow.mark(cur,'Opened');go(1);};
    box.addEventListener('keydown',function(e){
      var t=e.target,k=e.key;
      if(k==='Tab'){  // focus stays in the open panel: Tab and Shift+Tab cycle its controls
        var f=[].filter.call(box.querySelectorAll('a[href],button'),function(x){return x.offsetParent;}),a=f.indexOf(t);
        e.preventDefault();if(f.length)f[e.shiftKey?(a<=0?f.length-1:a-1):(a+1)%f.length].focus();return;}
      if(e.metaKey||e.ctrlKey||e.altKey||/^(INPUT|TEXTAREA|SELECT)$/.test(t.tagName))return;
      if(k==='Escape'&&document.querySelector('#rpop:not([hidden])'))return;  // the range map over the panel closes first
      if(k==='u'){var u=IdentifyFlow.undo();if(u){e.preventDefault();e.stopPropagation();open(u);}return;}
      var d={ArrowUp:-1,ArrowDown:1}[k];
      if(d){e.preventDefault();pick_(Math.max(0,Math.min(rows.length-1,act+d)));return;}
      d={ArrowLeft:-1,ArrowRight:1}[k];
      if(d){e.preventDefault();if(e.shiftKey)ZM.step(d);else RF.step(rows[act],d);return;}
      if(k==='z'){e.preventDefault();ZM.toggle();return;}
      var b={Escape:'#cpx',j:'#cpj',k:'#cpk',s:'#cps',c:'#cpc .copy',Enter:t.closest('button,a')?null:'#cpo'}[k];
      b=b&&box.querySelector(b);if(!b)return;
      e.preventDefault();e.stopPropagation();b.click();
    });
  }
  function go(d){
    var all=cards(),at=all.indexOf(cur);
    if(d>0&&at===all.length-1&&ctx.more){ctx.more();all=cards();}
    var n=all[at+d];if(n)open(n);else if(d>0)close();
  }
  function close(){if(!box||box.hidden)return;box.hidden=true;if(ctx.lend)ctx.lend(null);document.body.classList.remove('cpon');
    if(cur&&cur.isConnected){cur.focus({preventScroll:true});cur.scrollIntoView({block:'nearest'});}cur=null;}
  // the candidate on show: its row is ringed and its photos answer the arrow keys
  var rows=[],act=0,ZM=IdentifyZoom(TXT,size),
    RF=IdentifyRefs({T:TXT,size:size,link:IdentifyFlow.link,range:function(){return ctx.range?ctx.range():null;}});
  function pick_(k){
    if(k<0||k>=rows.length)return;
    act=k;rows.forEach(function(c,j){c.classList.toggle('on',j===k);if(j===k)c.setAttribute('aria-current','true');else c.removeAttribute('aria-current');});
    rows[k].scrollIntoView({block:'nearest'});
  }
  // the species and its closest look-alikes, whole; the same promise for a repeat
  var sims=new Map();
  function similar(t){
    if(!t[2])return Promise.resolve([]);
    if(!sims.has(t[2]))sims.set(t[2],taxa([t[2]],now).then(function(){return now('identifications/similar_species?taxon_id='+t[2]).catch(function(){return {};});})
      .then(function(j){var sim=(j.results||[]).slice(0,ROWS).map(function(x){return x.taxon;}).filter(Boolean);
        return taxa(sim.map(function(x){return x.id;}),now).then(function(){return sim;});}));
    return sims.get(t[2]);
  }
  // the runner-up whole: from the taxa table, else iNaturalist's taxon of that exact name, else the name alone
  var rivals=new Map();
  function rival(name){
    if(!rivals.has(name)){var r=row.get(name),id=r===undefined?0:T[r][2];
      rivals.set(name,(id?taxa([id],now).then(function(){return full.get(id);})
        :now('taxa?rank=species&per_page=1&q='+encodeURIComponent(name)).then(function(j){var x=(j.results||[])[0];
          if(x&&x.name===name){full.set(x.id,x);return x;}}).catch(function(){}))
        .then(function(x){return x||{id:id,name:name};}));}
    return rivals.get(name);
  }
  function why(li){return li.dataset.lv==='3'&&ctx.why?ctx.why(+li.dataset.i):null;}
  function role(li){return li.dataset.lv==='3'?TXT.role.suggested:li.dataset.lv==='1'?TXT.role.label:TXT.role.lookalike;}
  function refs(li){
    var t=named(li),r=box.querySelector('#cprefs'),id=li.dataset.id,y=why(li),i=+li.dataset.i;r.replaceChildren();rows=[];
    if(!t){r.append(el('p','muted',TXT.noSpecies));return;}
    r.append(el('p','muted',TXT.loading));
    Promise.all([similar(t),y&&rival(y[0])]).then(function(d){if(!cur||cur.dataset.id!==id)return;
        var main=full.get(t[2])||{id:t[2],name:t[0],preferred_common_name:t[1]},rv=d[1],sim=d[0],list=[[main,role(li)]];
        if(rv)list.push([rv,TXT.role.runnerup]);
        sim.filter(function(s){return s.name!==main.name&&!(rv&&s.name===rv.name);}).forEach(function(s){list.push([full.get(s.id)||s,TXT.role.similar]);});
        list=list.slice(0,ROWS);r.replaceChildren();  // as many as fit a phone's scroll; the order is the data's
        rows=list.map(function(x){return RF.row(x[0],x[1],i);});r.append.apply(r,rows);rows.forEach(RF.paint);
        if(list.length===1&&!rv&&t[2])r.append(el('p','muted',TXT.noSimilar));
        pick_(0);
        cards().slice(cards().indexOf(li)+1,cards().indexOf(li)+1+AHEAD).forEach(function(n){  // the next cards', ahead
          var nt=named(n),ny=why(n);if(nt)similar(nt);if(ny)rival(ny[0]);});});
  }
  // the observation the cards' request has not brought (yet): asked on the panel's own queue, null once iNaturalist has none
  var own=new Map();
  function fetchObs(li){
    var id=+li.dataset.id;if(own.has(id))return;own.set(id,undefined);
    now('observations?id='+id).then(function(j){own.set(id,(j.results||[])[0]||null);},function(){own.set(id,null);})
      .then(function(){if(cur===li)obs(li);});
  }
  function obs(li){
    var id=+li.dataset.id,o=ctx.obs(id)||own.get(id),v=box.querySelector('#cpobs'),ps=o&&o.photos||[],w=el('a','cpwhen');
    v.replaceChildren();
    if(!o&&own.get(id)===undefined)fetchObs(li);
    if(!ps.length){v.append(el('p','muted',o||own.get(id)===null?TXT.noObs:TXT.loadingObs));return;}
    w.href=li.querySelector('.when').href;w.textContent=(o.observed_on||TXT.dateUnknown)+' · '+(o.place_guess||TXT.placeUnknown);IdentifyFlow.link(w);
    v.append(ZM.view(ps),w);
  }
  // quiet: the pick came from another pane, so it is not told back
  function open(li,quiet){
    if(!box)build();
    cur=li;var all=cards(),t=named(li),c=box.querySelector('#cpc'),nm=li.querySelector('.title i');
    var h=box.querySelector('#cphead');h.replaceChildren(el('i',null,nm?nm.textContent:'Record'));
    if(t&&li.dataset.lv!=='1')h.append(' → ',el('i',null,t[0]),'?');
    box.querySelector('#cpat').textContent=(all.indexOf(li)+1)+' of '+all.length+' shown';
    box.querySelector('#cplive').textContent=(all.indexOf(li)+1)+' of '+all.length+', '+(nm?nm.textContent:'Record')+(t&&li.dataset.lv!=='1'?' to '+t[0]:'');
    c.replaceChildren();if(t)c.append(IdentifyNarrow.copy(t[0]));
    var y=why(li),wy=box.querySelector('#cpwhy');wy.replaceChildren();if(y)wy.append(IdentifyNarrow.why(y[0],y[1]));
    obs(li);refs(li);if(ctx.lend)ctx.lend(li,box.querySelector('#cpdet'));
    box.hidden=false;document.body.classList.add('cpon');li.scrollIntoView({block:'nearest'});
    [].forEach.call(document.querySelectorAll('.card.cur'),function(x){x.classList.remove('cur');});li.classList.add('cur');
    if(!box.contains(document.activeElement)||document.activeElement===box)box.focus({preventScroll:true});box.scrollTop=0;  // a button in use keeps focus; #cplive names the card
    if(!quiet&&parent!==window)parent.postMessage({type:'wtid-record',id:+li.dataset.id},location.origin);  // j, k, Skip and Enter move the map's card too
  }
  // a record picked in another pane: its card here is ringed and scrolled to, and the open panel moves to it; nothing if it is not drawn
  function pick(id){
    var li=id!=null&&document.querySelector('#grid .card[data-id="'+id+'"],#sgrid .card[data-id="'+id+'"]');
    if(!li||li===cur&&shown())return;
    if(shown())open(li,true);
    else{[].forEach.call(document.querySelectorAll('.card.cur'),function(x){x.classList.remove('cur');});li.classList.add('cur');li.scrollIntoView({block:'nearest'});}
  }
  function shown(){return box&&!box.hidden?cur:null;}
  // the cards' request brought the observation: the panel showing it fills in
  function landed(li){if(box&&!box.hidden&&cur===li)obs(li);}
  return {ref:rival,fill:fill,pair:pair,open:open,close:close,landed:landed,pick:pick,shown:shown};
};
})();
