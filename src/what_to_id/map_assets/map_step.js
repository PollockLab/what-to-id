// The Identify button for an exact link in several batches: it names the batch it opens, each click
// opens that batch in a new tab and moves on to the next, stopping at the last, and ‹ › step by hand.
// The batches opened are kept in localStorage per selection and build, so coming back to the same
// records on the same build starts at the first batch not yet opened, and a new build starts over.
// Storage that throws only loses that memory across visits. Progress never goes into the URL hash,
// so a shared link opens at batch 1.
var IdStep=(function(){
'use strict';
var PRE='idstep:';
// o: a (the Identify anchor), prev and next (the ‹ › buttons), build (the build's date) and store()
// (localStorage unless given).
function IdStep(o){
  var a=o.a,label=a.textContent,store=o.store||function(){return localStorage;},pre=PRE+o.build+':',
    MEM={},KEY='',LIST=[],K=0,k=1,CUR=0;
  // what older builds remembered no longer names the same batches
  try{var s=store(),old=[];for(var i=0;i<s.length;i++){var n=s.key(i);
    if(n.indexOf(PRE)===0&&n.indexOf(pre)!==0)old.push(n);}
    old.forEach(function(n){s.removeItem(n);});}catch(e){}
  // the batch numbers opened for this selection, read from storage once and kept in memory
  function done(){if(!MEM[KEY]){var d={};
      try{(store().getItem(pre+KEY)||'').split(',').forEach(function(x){if(+x)d[+x]=1;});}catch(e){}
      MEM[KEY]=d;}
    return MEM[KEY];}
  function first(){var d=done();for(var j=1;j<K;j++)if(!d[j])return j;return K;}
  function show(){o.prev.hidden=o.next.hidden=K<2;
    if(K<2){a.textContent=label;return;}
    a.textContent='Open in Identify · batch '+k+' of '+K;a.href=LIST[k-1].url;
    o.prev.disabled=k<=1;o.next.disabled=k>=K;}
  function go(j){k=CUR=Math.max(1,Math.min(K,j));show();}
  // The browser opens the href once the click handlers return, so the label and href move on after.
  function open(){if(K<2)return;var d=done();d[k]=1;
    try{store().setItem(pre+KEY,Object.keys(d).join(','));}catch(e){}
    k=CUR=Math.min(K,k+1);setTimeout(show,0);}
  a.addEventListener('click',open);
  a.addEventListener('auxclick',function(e){if(e.button===1)open();});
  o.prev.addEventListener('click',function(){go(k-1);});
  o.next.addEventListener('click',function(){go(k+1);});
  return {
    // The batches for selection key, or fewer than two for a single link u; returns the href.
    // Until the viewer steps, the batch shown is the first not yet opened, kept as more records load.
    set:function(key,list,u){if(key!==KEY){KEY=key;CUR=0;}LIST=list;K=list.length>1?list.length:0;
      k=!K?1:CUR?Math.min(CUR,K):first();show();return K?LIST[k-1].url:u;},
    open:open,go:go,
    at:function(){return [k,K];}
  };
}
return IdStep;
})();
