// Fewer tab switches on level 3: iNaturalist links share one window beside the list (named wtid-inat, opened as a half-screen popup
// and reused), Identify on a level 3 card first copies the suggested name, marks the card Opened and moves focus to the next card,
// and j, k, i (or Enter) and c work the cards from the keyboard. A blocked popup or a modified click falls back to the link itself.
var IdentifyFlow=(function(){
'use strict';
var NAME='wtid-inat',OPENED=new Set();
function el(tag,cls,text){var e=document.createElement(tag);if(cls)e.className=cls;if(text!=null)e.textContent=text;return e;}
// the right half of the screen, full height
function feat(){
  var s=window.screen,w=Math.floor(s.availWidth/2);
  return 'popup,width='+w+',height='+s.availHeight+',left='+((s.availLeft||0)+s.availWidth-w)+',top='+(s.availTop||0);
}
// The popup keeps its opener, which is how the named window is found again; the link itself (a blocked popup, middle click) opens noopener.
function link(a,then){
  a.target=NAME;a.rel='noopener';
  a.addEventListener('click',function(e){
    if(e.defaultPrevented||e.button||e.metaKey||e.ctrlKey||e.shiftKey||e.altKey)return;
    if(then)then();
    var w=window.open(a.href,NAME,feat());
    if(w){if(w.focus)w.focus();e.preventDefault();}
  });
}
function mark(li){
  if(li.querySelector('.opened'))return;
  var w=li.querySelector('.when');li.insertBefore(el('div','badge opened','Opened'),w);
}
function next(li){
  var n=li.nextElementSibling;
  while(n&&!n.classList.contains('card'))n=n.nextElementSibling;
  if(n){n.focus({preventScroll:true});n.scrollIntoView({block:'nearest'});}
}
return {
  link:link,
  // the Identify link of a level 3 card
  identify:function(a,li){
    link(a,function(){var c=li.querySelector('.copy');if(c)c.click();OPENED.add(li.dataset.id);mark(li);next(li);});
    if(OPENED.has(li.dataset.id))mark(li);
  },
  // ctx {level(), more()}: the keys work on level 3 only, never in a form field
  keys:function(ctx){
    document.addEventListener('keydown',function(e){
      var t=e.target,k=e.key.toLowerCase();
      if(ctx.level()!==3||e.metaKey||e.ctrlKey||e.altKey||/^(INPUT|TEXTAREA|SELECT)$/.test(t.tagName)||t.isContentEditable)return;
      var cards=[].slice.call(document.querySelectorAll('#grid .card')),cur=document.activeElement.closest('.card'),at=cards.indexOf(cur),c;
      if(k==='j'||k==='k'){
        e.preventDefault();
        if(k==='j'&&at===cards.length-1){ctx.more();cards=[].slice.call(document.querySelectorAll('#grid .card'));}
        c=cards[Math.max(0,Math.min(cards.length-1,at+(k==='j'?1:-1)))];
        if(c){c.focus({preventScroll:true});c.scrollIntoView({block:'nearest'});}
      }else if(cur&&(k==='i'||k==='enter'&&t===cur)){e.preventDefault();var a=cur.querySelector('a.btn');if(a)a.click();}
      else if(cur&&k==='c'){c=cur.querySelector('.copy');if(c){e.preventDefault();c.click();}}
    });
  },
  draw:function(lv){var h=document.getElementById('keys');if(h)h.hidden=lv!==3;}
};
})();
