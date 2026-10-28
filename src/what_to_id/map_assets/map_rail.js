// Explore's filter rail, in the embedded map only: the filters are a column left of the map, open at
// 1280 px and wider unless the viewer folded it (kept as 'wtid-rail'), and its head button folds it to a
// strip with a Filters button. The shell sizes the frame by the open state (wtid-rail). With the map
// pane hidden the shell keeps this frame as the rail alone (wtid-rail only), which counts all of BC;
// on a phone the rail is a sheet, opened by the shell's Filters button (wtid-rail open).
(function(){
'use strict';
var H=document.documentElement;if(!H.classList.contains('embed'))return;
var KEY='wtid-rail',side=document.getElementById('side'),btn=document.getElementById('railx'),
  scope=document.getElementById('scope').children,ours=false,NARROW=matchMedia('(max-width:760px)'),saved=null;
try{saved=localStorage.getItem(KEY);}catch(e){}
function wide(){try{return parent.innerWidth>=1280;}catch(e){return innerWidth>=1280;}}
function set(v,keep){
  H.classList.toggle('rail-off',!v);side.classList.toggle('open',v);
  btn.setAttribute('aria-expanded',String(v));btn.textContent=v?'Hide':'Filters';
  btn.setAttribute('aria-label',v?'Hide the filters':'Show the filters');
  if(keep&&!NARROW.matches)try{localStorage.setItem(KEY,v?'1':'0');}catch(e){}
  if(parent!==window)parent.postMessage({type:'wtid-rail',open:v,shut:!!keep&&!v},location.origin);  // shut: the viewer closed it
  dispatchEvent(new Event('resize'));}  // the map and the histograms take the new width
btn.onclick=function(){set(H.classList.contains('rail-off'),true);};
set(!NARROW.matches&&(saved?saved==='1':wide()),false);  // a phone opens with the sheet shut
addEventListener('message',function(e){
  var d=e.data;if(e.origin!==location.origin||e.source!==parent||!d||d.type!=='wtid-rail')return;
  if(typeof d.only==='boolean'&&d.only!==H.classList.contains('rail-only')){H.classList.toggle('rail-only',d.only);
    // alone, the rail counts all of BC; with the map back the switch returns to In view if it was there
    if(d.only&&scope[0].getAttribute('aria-pressed')==='true'){ours=true;scope[1].click();}
    else if(!d.only&&ours){ours=false;scope[0].click();}}
  if(d.open===true)set(true,false);
});
})();
