// The life groups' share bar, the summary of the groups section as on the map's rail (group_list.js): one segment per
// group with points in view, widths the shares, MapFilter colours, the picked groups full and the rest dimmed. The
// section opens wide on a standalone page and starts folded when narrow or beside other panes; a click on the summary
// (the bar included) is remembered in this browser, blocked storage keeps nothing.
// o: det (the <details>), bar (the summary's bar), G (group keys), name(j), color(j) ('rgb(...)'), nf, S (the filters).
// set(count) draws the bar from the points in view per group.
var GroupBar=(function(){
'use strict';
var KEY='wtid-space-groups';
function saved(){try{return localStorage.getItem(KEY);}catch(e){return null;}}
function GroupBar(o){
  var d=o.det,narrow=/(^|\s)(embed|peer)(\s|$)/.test(document.documentElement.className)||innerWidth<=760;
  d.open=saved()?saved()==='open':!narrow;
  d.querySelector('summary').addEventListener('click',function(){
    try{localStorage.setItem(KEY,d.open?'closed':'open');}catch(e){}});  // the click comes before the toggle
  function set(c){
    var tot=0,top=[],j,inc=o.G.some(function(g){return o.S.groups[g]==='inc';});
    for(j=0;j<c.length;j++)tot+=c[j];
    o.bar.textContent='';
    o.G.map(function(g,k){return k;}).sort(function(a,b){return c[b]-c[a]||a-b;}).forEach(function(k){
      if(!c[k])return;var s=document.createElement('i'),st=o.S.groups[o.G[k]],p=(c[k]/tot*100).toFixed(1)+'%';
      s.style.background=o.color(k);s.style.width=c[k]/tot*100+'%';
      if(inc?st!=='inc':st==='not')s.className='dim';
      s.title=o.name(k)+', '+o.nf.format(c[k])+' ('+p+')';o.bar.appendChild(s);
      if(top.length<3)top.push(o.name(k)+' '+p);});
    o.bar.setAttribute('aria-label',top.length?'Largest groups in view: '+top.join(', '):'No points in view');
  }
  return {set:set};
}
return GroupBar;
})();
