// Explore's state bar: one pill over every pane, bottom centre, with the map's record count, the chips of the
// map's selection bar (#selbar, read in place; a chip's × clicks that chip's own ×, so the change goes through
// the map's sync to every pane and the address) and the Legend and Filters buttons. Those open the map frame's
// sheet (map_sheet.js), one at a time: over the map pane, or with the map pane hidden the map's frame itself as
// the page's sheet. o: frames, visible(n), make() (makes the map's frame), post(n,m), rail() (shows the frame).
function StateBar(o){
'use strict';
var $=function(id){return document.getElementById(id);},num=$('sbn'),ul=$('sbc'),open=null,sig=null,
  bs={legend:$('sbl'),filters:$('sbf')};
function doc(){try{return o.frames.map.contentDocument;}catch(e){return null;}}
function set(k){open=k;if(k&&!o.frames.map)o.make();
  for(var b in bs)bs[b].setAttribute('aria-expanded',String(open===b));
  o.rail();}
// rail() calls this once it has sized the map's frame: the frame as the sheet when its pane is hidden.
function send(){var f=o.frames.map;if(!f)return;
  if(!o.visible('map')){f.classList.toggle('sheet',!!open);if(open)f.hidden=false;}
  if(!f.classList.contains('sheet'))f.style.height='';else fit();
  o.post('map',{type:'wtid-sheet',open:open});}
// The frame as the sheet is as tall as what it shows (the rail then the panel), 60vh at most (split.html).
var ro=null;
function fit(){var f=o.frames.map,x=doc()&&doc().getElementById('xsheet');
  if(f&&x&&f.classList.contains('sheet'))f.style.height=Math.ceil(x.offsetTop+x.offsetHeight)+'px';}
Object.keys(bs).forEach(function(k){bs[k].onclick=function(){set(open===k?null:k);};});
addEventListener('keydown',function(e){if(e.key==='Escape'&&open)set(null);});
addEventListener('message',function(e){var d=e.data;
  if(e.origin===location.origin&&o.frames.map&&e.source===o.frames.map.contentWindow&&d&&d.type==='wtid-sheet'&&
    d.open===null&&open)set(null);});  // the frame's Esc
function tick(){
  var d=doc(),x=d&&d.getElementById('xsheet');
  if(x&&(!ro||ro.x!==x)){ro=new d.defaultView.ResizeObserver(fit);ro.x=x;ro.observe(x);ro.observe(d.getElementById('side'));}
  var c=d&&d.getElementById('count'),t=c&&/\d/.test(c.textContent)?c.textContent.replace(/ records?$/,''):'';
  if(num.textContent!==t)num.textContent=t;
  // a frame too narrow for its rail (map_sheet.js) puts What in the sheet too, so the button holds every filter
  var w=d&&d.defaultView.matchMedia('(max-width:760px)').matches&&!d.documentElement.classList.contains('rail-only'),
    lb=!d||w?'Filters':'When & where';if(bs.filters.textContent!==lb)bs.filters.textContent=lb;
  var li=d?[].slice.call(d.querySelectorAll('#selbar li')):[],
    s=li.map(function(x){return x.firstChild.textContent+(x.querySelector('.x')?'×':'');}).join('\n');
  if(s===sig)return;sig=s;ul.textContent='';
  li.forEach(function(x,j){var c=ul.appendChild(document.createElement('li')),fx=x.querySelector('.x');
    c.appendChild(document.createElement('span')).textContent=x.firstChild.textContent;if(!fx)return;
    var b=c.appendChild(document.createElement('button'));b.type='button';b.textContent='×';
    b.setAttribute('aria-label',fx.getAttribute('aria-label'));
    b.onclick=function(){var y=(doc()||document).querySelectorAll('#selbar li')[j],z=y&&y.querySelector('.x');
      if(z)z.click();};});}
setInterval(tick,400);tick();
return {send:send,close:function(){if(open)set(null);}};
}
