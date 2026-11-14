// The card's resize edge, split from embeddings_app.js; el and $ are the page's.
function CardSize(el,$){
// The card's left edge: drag it, or use the arrow keys; a double click goes back to the default. The width is remembered.
function cardWidth(w){
  var c=$('card');if(w==null){c.style.width='';localStorage.removeItem('wtid-card');return;}
  w=Math.max(240,Math.min(innerWidth*0.7,w));c.style.width=w+'px';localStorage.setItem('wtid-card',w);
}
if(+localStorage.getItem('wtid-card'))cardWidth(+localStorage.getItem('wtid-card'));
function resizer(){
  var rz=el('button',{type:'button','class':'rz','aria-label':'Resize the card'});
  // preventDefault: otherwise the photo under the edge starts a native image drag and cancels the pointer
  rz.addEventListener('pointerdown',function(e){e.preventDefault();rz.setPointerCapture(e.pointerId);rz.classList.add('on');});
  rz.addEventListener('pointermove',function(e){if(rz.classList.contains('on'))cardWidth($('card').getBoundingClientRect().right-e.clientX);});
  rz.addEventListener('pointerup',function(){rz.classList.remove('on');});
  rz.addEventListener('dblclick',function(){cardWidth(null);});
  rz.addEventListener('keydown',function(e){
    var d={ArrowLeft:20,ArrowRight:-20}[e.key];if(d){cardWidth($('card').getBoundingClientRect().width+d);e.preventDefault();}
    else if(e.key==='Home'){cardWidth(null);e.preventDefault();}});
  return rz;
}
return resizer;
}
