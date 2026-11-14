// The record's photos in the compare panel: one large photo that zooms to 2.5x under the pointer (a click, a tap or z), and
// a strip of thumbnails. IdentifyZoom(T, size) with T the panel's strings (IdentifyText) and size(url, name) the iNaturalist
// photo size swap. view(photos) returns a fresh element holding them; step(d) moves to the next or previous photo and
// toggle() zooms, both for the keys.
var IdentifyZoom=(function(){
'use strict';
function el(tag,cls){var e=document.createElement(tag);if(cls)e.className=cls;return e;}
return function(T,size){
  var ps=[],at=0,zoomed=false,st,img,thumbs=[];
  function zoom(on){
    zoomed=on;st.classList.toggle('zoom',on);st.setAttribute('aria-pressed',String(on));
    st.setAttribute('aria-label',(on?T.zoomOut:T.zoomIn)(at+1,ps.length));if(!on)img.style.transformOrigin='';
  }
  function origin(e){var r=st.getBoundingClientRect();
    img.style.transformOrigin=(100*(e.clientX-r.left)/r.width)+'% '+(100*(e.clientY-r.top)/r.height)+'%';}
  function show(k){
    at=(k+ps.length)%ps.length;img.src=size(ps[at].url,'large');img.alt=T.obsPhoto(at+1,ps.length);zoom(false);
    thumbs.forEach(function(b,j){b.setAttribute('aria-pressed',String(j===at));});
    if(ps.length>1)new Image().src=size(ps[(at+1)%ps.length].url,'large');  // the next one is already there when asked for
  }
  return {
    view:function(photos){
      var v=el('div','cpview'),strip=el('div','cpstrip');ps=photos;thumbs=[];st=el('button','cpstage');img=el('img','cpbig');
      st.type='button';st.append(img);
      st.onclick=function(e){if(!zoomed&&e.detail)origin(e);zoom(!zoomed);};
      st.onpointermove=function(e){if(zoomed)origin(e);};  // a drag pans on touch (touch-action: none while zoomed)
      photos.forEach(function(p,k){var b=el('button','cpthumb'),t=el('img');b.type='button';b.setAttribute('aria-label',T.thumb(k+1,photos.length));
        t.src=size(p.url,'square');t.alt='';b.append(t);b.onclick=function(){show(k);};thumbs.push(b);strip.append(b);});
      v.append(st);if(photos.length>1)v.append(strip);
      show(0);return v;
    },
    step:function(d){if(ps.length>1)show(at+d);},
    toggle:function(){if(st&&st.isConnected)zoom(!zoomed);}
  };
};
})();
