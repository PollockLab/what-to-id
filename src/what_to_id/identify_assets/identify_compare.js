// Reference photos on the cards that name a look-alike: the label's and the look-alike's iNaturalist default photo side by
// side under the record's photo, so the call is made against examples rather than a name alone.
// IdentifyCompare(ctx), ctx {taxa (the TAXA table), tax (each record's taxa row), look(i)}. fill(lis) adds them to the
// cards just drawn, 30 taxa to a request. Needs map_user.js (inatGate).
var IdentifyCompare=(function(){
'use strict';
var MAX=30,NOTAX=65535;
function el(tag,cls,text){var e=document.createElement(tag);if(cls)e.className=cls;if(text!=null)e.textContent=text;return e;}
return function(ctx){
  var T=ctx.taxa,row=new Map(),photo=new Map(),api=inatGate({gap:1000});
  T.forEach(function(t,r){row.set(t[0],r);});
  // [label taxa row, look-alike taxa row] for a card that names a look-alike in the taxa table, else null
  function pair(i){
    var l=ctx.look(i),a=ctx.tax[i],b=l==null?undefined:row.get(l);
    return a!==NOTAX&&a<T.length&&b!==undefined?[a,b]:null;
  }
  function fig(r,cap){
    var f=el('figure'),img=el('img');
    img.loading='lazy';img.alt=cap+' '+T[r][0]+', reference photo';img.dataset.t=T[r][2];
    f.append(img,el('figcaption',null,cap));f.title=T[r][0];show(img);
    return f;
  }
  // the photo once known: a URL, or '' for none
  function show(img){
    var p=photo.get(+img.dataset.t);if(p===undefined||img.src)return;
    if(p)img.src=p;else img.parentNode.title+=' (no reference photo)';
  }
  // the boxes go in at once, their size fixed, so the photos landing later do not move the card
  function fill(lis){
    var want=[],seen=new Set(),imgs=[];
    lis.forEach(function(li){var pr=pair(+li.dataset.i);if(!pr)return;
      var old=li.querySelector('.cmp'),box=el('div','cmp');
      box.append(fig(pr[0],'Label'),fig(pr[1],'Look-alike'));
      if(old)old.replaceWith(box);else li.querySelector('.title').after(box);
      imgs.push.apply(imgs,box.querySelectorAll('img'));
      pr.forEach(function(r){var id=T[r][2];if(!photo.has(id)&&!seen.has(id)){seen.add(id);want.push(id);}});});
    var asks=[];
    for(var k=0;k<want.length;k+=MAX)asks.push(api('taxa/'+want.slice(k,k+MAX).join(',')).then(function(j){
      (j.results||[]).forEach(function(t){var d=t.default_photo;photo.set(t.id,d&&d.square_url?String(d.square_url).replace('/square.','/small.'):'');});}));
    return Promise.all(asks).catch(function(){}).then(function(){
      want.forEach(function(id){if(!photo.has(id))photo.set(id,'');});
      imgs.forEach(show);});
  }
  return {fill:fill,pair:pair};
};
})();
