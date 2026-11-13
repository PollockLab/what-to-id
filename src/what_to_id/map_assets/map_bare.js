// Identify's Where panel, the bare map (embed=1&bare=1, map_bare.css): Esc in this frame never reaches the page, so it tells
// the page, which shrinks an expanded map. Esc that ends a drawing or shuts the parks list is theirs.
(function(){
'use strict';
if(!document.documentElement.classList.contains('bare'))return;
addEventListener('keydown',function(e){
  var cancel=document.querySelector('.area [data-a=cancel]');
  if(e.key!=='Escape'||cancel&&!cancel.hidden||e.target.closest&&e.target.closest('[aria-expanded=true]'))return;
  parent.postMessage({type:'wtid-bare',esc:true},location.origin);
});
})();
