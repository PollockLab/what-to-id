// "Research Grade here" (All / None yet) in #rg, over the area. None yet keeps the records whose taxon, rolled up to its species,
// has no Research Grade iNaturalist observation inside the area's bounding box; records labelled above species do not pass.
// The species with a record come from species_counts, read when None yet is picked and again when the area changes (hash: rg=none).
// IdentifyUnconfirmed(ctx), ctx {P, taxa (the TAXA table), ranks, area() the area string, redraw()}. Needs map_user.js (inatGate, usrPages).
var IdentifyUnconfirmed=(function(){
'use strict';
var CAP=10,PER=500,HINT='Species with no Research Grade record in this area yet. Your ID could be its first.',nf=new Intl.NumberFormat('en-CA');
function $(id){return document.getElementById(id);}
function el(tag,cls,text){var e=document.createElement(tag);if(cls)e.className=cls;if(text!=null)e.textContent=text;return e;}
// [swlat, swlng, nelat, nelng] of the area's rings, null for none or a string that does not decode
function box(a){
  if(!a)return null;
  try{var b=[Infinity,Infinity,-Infinity,-Infinity];
    MapArea.decode(a).forEach(function(r){for(var k=0;k<r.length;k+=2){
      b[0]=Math.min(b[0],r[k+1]);b[1]=Math.min(b[1],r[k]);b[2]=Math.max(b[2],r[k+1]);b[3]=Math.max(b[3],r[k]);}});
    return b[0]<=b[2]?b:null;}catch(e){return null;}
}
return function(ctx){
  var T=ctx.taxa,tax=ctx.P.tax,species=new Set(),memo=new Map(),on=/(?:^|&)rg=none(?:&|$)/.test(location.hash.slice(1)),
    have=null,key='',bad='',err='',run=0,capped=false,SEG,note,
    api=inatGate({say:function(t){note.textContent=t;}});
  T.forEach(function(t){if(ctx.ranks[t[3]]==='species')species.add(t[2]);});
  // a taxa row's species (its iNaturalist id), 0 when the row is above species
  function up(r){
    if(r>=T.length)return 0;
    var g=memo.get(r);if(g!==undefined)return g;
    g=ctx.ranks[T[r][3]]==='species'?T[r][2]:T[r][4]>=0?up(T[r][4]):0;memo.set(r,g);return g;
  }
  function ready(){return !!have&&have.key===ctx.area();}
  // no filtering until the species are read
  function pass(i){if(!on||!ready())return true;var s=up(tax[i]);return !!s&&!have.set.has(s);}
  function load(a,b){
    key=a;have=null;
    var me=++run,live=function(){return me===run;},
      q='observations/species_counts?quality_grade=research&verifiable=true&swlat='+b[0].toFixed(4)+'&swlng='+b[1].toFixed(4)+
        '&nelat='+b[2].toFixed(4)+'&nelng='+b[3].toFixed(4)+'&per_page='+PER+'&page=';
    usrPages(function(n){return api(q+n,live);},CAP,PER).then(function(r){
      if(!live())return;
      var s=new Set();
      r.items.forEach(function(x){var t=x.taxon||{};
        if(t.rank==='species')s.add(t.id);
        else(t.ancestor_ids||[]).forEach(function(id){if(species.has(id))s.add(id);});});
      have={key:a,set:s};capped=r.capped;ctx.redraw();
    }).catch(function(e){if(!live())return;bad=a;key='';err='Could not read iNaturalist ('+e.message+'). Showing all.';ctx.redraw();});
  }
  function hash(){
    var t=location.hash.slice(1).split('&').filter(function(x){return x&&x.indexOf('rg=')!==0;});
    if(on)t.push('rg=none');
    history.replaceState(null,'','#'+t.join('&'));
  }
  var OPTS=[[false,'All'],[true,'None yet']];
  function seg(){
    var g=$('rg');
    if(!g)return null;
    var r=el('div','seg');r.setAttribute('role','radiogroup');r.setAttribute('aria-label','Research Grade here');
    OPTS.forEach(function(x){
      var b=el('button','segb');b.type='button';b.setAttribute('role','radio');
      b.onclick=function(){on=x[0];bad=err='';hash();ctx.redraw();};
      r.appendChild(b);});
    r.onkeydown=function(e){
      var k=['ArrowLeft','ArrowUp','ArrowRight','ArrowDown','Home','End'].indexOf(e.key),
        all=[].slice.call(r.children),at=all.indexOf(document.activeElement);
      if(k<0||at<0)return;e.preventDefault();
      var to=k===4?0:k===5?all.length-1:(at+(k%4<2?-1:1)+all.length)%all.length;
      all[to].focus();all[to].click();
    };
    note=el('span','segnote');
    g.append(el('span',null,'Research Grade here: '),r,note);
    return r;
  }
  SEG=seg();
  return {
    pass:pass,
    // the control and its counts, over the selected records of the level; hidden with no area
    draw:function(lv,sel,level){
      if(!SEG)return;
      var a=ctx.area(),b=box(a);
      $('rg').hidden=!b;
      if(!b)return;
      if(on&&!ready()&&a!==key&&a!==bad)load(a,b);
      var t=0,k=0;
      for(var i=0;i<ctx.P.n;i++)if(sel[i]&&level[i]===lv){t++;if(pass(i))k++;}
      var c=[nf.format(t),on&&ready()?' '+nf.format(k):on&&!err?' …':''];
      [].forEach.call(SEG.children,function(x,j){
        x.textContent=OPTS[j][1]+(j?c[1]:' '+c[0]);
        x.setAttribute('aria-checked',String(OPTS[j][0]===on));x.tabIndex=OPTS[j][0]===on?0:-1;});
      note.textContent=err||(on&&!ready()?'Reading Research Grade records in this area…':HINT+(on&&capped?
        ' Only the first '+nf.format(CAP*PER)+' species with one were read, so some listed here may have one.':''));
    }
  };
};
})();
