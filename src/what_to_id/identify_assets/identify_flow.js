// Fewer tab switches on level 3: iNaturalist links share one tab (named wtid-inat, reused), Identify on a level 3 card first copies the suggested name, marks the card Opened and moves focus to the next card,
// and j, k, i (or Enter) and c work the cards from the keyboard. A blocked open or a modified click falls back to the link itself.
var IdentifyFlow=(function(){
'use strict';
var NAME='wtid-inat',DONE=new Map();
function el(tag,cls,text){var e=document.createElement(tag);if(cls)e.className=cls;if(text!=null)e.textContent=text;return e;}
// A named tab is found again by its name; the link itself (a blocked open, middle click) opens noopener.
function link(a,then){
  a.target=NAME;a.rel='noopener';
  a.addEventListener('click',function(e){
    if(e.defaultPrevented||e.button||e.metaKey||e.ctrlKey||e.shiftKey||e.altKey)return;
    if(then)then();
    var w=window.open(a.href,NAME);
    if(w){if(w.focus)w.focus();e.preventDefault();}
  });
}
// a card done with: Opened or Skipped, kept across redraws
function mark(li,text){
  text=text||'Opened';DONE.set(li.dataset.id,text);li.classList.add('done');
  var b=li.querySelector('.opened');if(b){if(text==='Opened')b.textContent=text;return;}
  li.insertBefore(el('div','badge opened',text),li.querySelector('.when'));
}
function next(li){
  var n=li.nextElementSibling;
  while(n&&!n.classList.contains('card'))n=n.nextElementSibling;
  if(n){n.focus({preventScroll:true});n.scrollIntoView({block:'nearest'});}
}
function seen(li){if(DONE.has(li.dataset.id))mark(li,DONE.get(li.dataset.id));}
return {
  link:link,mark:mark,seen:seen,
  // the Identify link of a level 3 card
  identify:function(a,li){
    link(a,function(){var c=li.querySelector('.copy');if(c)c.click();mark(li);next(li);});
    seen(li);
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
