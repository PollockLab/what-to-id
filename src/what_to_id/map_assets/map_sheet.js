// Explore's sheet, in the embedded map only: the dates (#time), the area control (map_area.js) and the dots'
// legend (level_colour.js) leave their places for one panel, which the shell's state bar (state_bar.js) opens
// with {type:'wtid-sheet',open:'filters'|'legend'|null}. It sits over the foot of the map, or, with the map
// pane hidden, fills the frame the shell shows as a sheet. A frame too narrow for the rail (760 px) has the
// rail at the head of Filters, opened for it. Esc shuts it, and the shell is told.
(function(){
'use strict';
var H=document.documentElement;if(!H.classList.contains('embed'))return;
var p=document.createElement('section'),f=p.appendChild(document.createElement('div')),
  l=p.appendChild(document.createElement('div')),leg=document.querySelector('.lvleg'),
  area=document.querySelector('.maplibregl-ctrl.area'),none=document.createElement('p'),open=null,
  side=document.getElementById('side'),NARROW=matchMedia('(max-width:760px)'),ours=false;
p.id='xsheet';p.className='xsheet';p.hidden=true;p.setAttribute('role','region');
f.append(document.getElementById('time'));if(area)f.append(area);
if(leg)l.append(leg);
none.className='muted xnone';none.textContent='Each dot takes its group’s colour. Pick one group or taxon to colour its dots by clade.';
l.append(none);document.body.appendChild(p);
function place(){var only=H.classList.contains('rail-only'),on=open==='filters'&&NARROW.matches&&!only;
  if(on&&side.parentNode!==p){p.insertBefore(side,f);if(H.classList.contains('rail-off')){ours=true;flip();}}
  else if(!on&&side.parentNode===p){document.body.insertBefore(side,document.getElementById('map'));if(ours){ours=false;if(!only)flip();}}}  // alone, the rail stays open
function flip(){document.getElementById('railx').click();}
NARROW.addEventListener('change',place);new MutationObserver(place).observe(H,{attributes:true,attributeFilter:['class']});  // rail-only
function set(k,tell){open=k;place();p.hidden=!k;f.hidden=k!=='filters';l.hidden=k!=='legend';
  H.classList.toggle('sheet-f',k==='filters');H.classList.toggle('sheet-l',k==='legend');
  p.setAttribute('aria-label',k==='legend'?'Legend':side.parentNode===p?'Filters':'When and where');
  if(tell&&parent!==window)parent.postMessage({type:'wtid-sheet',open:k},location.origin);
  dispatchEvent(new Event('resize'));}  // the histograms take the panel's width
addEventListener('message',function(e){
  var d=e.data;if(e.origin!==location.origin||e.source!==parent||!d||d.type!=='wtid-sheet')return;
  var k=d.open==='filters'||d.open==='legend'?d.open:null;if(k!==open)set(k,false);
});
// Esc shuts the sheet, unless it steps the legend's pick up a level (focus in the legend, its trail shown),
// ends a drawing or shuts an open list.
addEventListener('keydown',function(e){
  if(e.key!=='Escape'||!open||leg&&!leg.hidden&&leg.contains(e.target)&&leg.querySelector('[aria-label="Legend trail"]')||area&&!area.querySelector('[data-a=cancel]').hidden||
    e.target.closest&&e.target.closest('[aria-expanded=true]'))return;
  set(null,true);},true);
})();
