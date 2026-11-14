// Photo-first cards: the photo fills the card and flips through the observation and the reference photos the compare boxes
// hold (.cmp: the suggestion or look-alike, then the label), with the runner-up between them once asked for. Arrows, the
// arrow keys on a focused card, and a swipe flip it. Under it one line names the species the card proposes ("<i>X</i>?"),
// a muted one where the claim comes from and the place, and a tag on the photo the margin bucket. The rest of the card
// (copy, Top N%, gap, range, common name, +N more, Agree) stays in the card, hidden, and is lent to the compare panel
// while it shows that card. IdentifyCard(ctx), ctx {ref(name) a promise of the taxon (iNaturalist API v1), or of {name}}.
var IdentifyCard=(function(){
'use strict';
var NS='http://www.w3.org/2000/svg';
function el(tag,cls,text){var e=document.createElement(tag);if(cls)e.className=cls;if(text!=null)e.textContent=text;return e;}
function svg(d){var s=document.createElementNS(NS,'svg'),p=document.createElementNS(NS,'path');s.setAttribute('viewBox','0 0 24 24');
  s.setAttribute('aria-hidden','true');p.setAttribute('d',d);s.appendChild(p);return s;}
function txt(li,sel){var e=li.querySelector(sel);return e?I18N.raw(e):'';}  // the English the modules wrote, whatever the page language
return function(ctx){
  var lent=[];
  // the frames in order: the observation, the proposed species, the runner-up, the label
  function frames(car){
    var f=car.querySelectorAll('.cmp figure');
    return [car.querySelector('.ph'),f[1],car.querySelector('.run'),f[0]].filter(Boolean);
  }
  function show(car,k){
    var fs=frames(car),n=fs.length;k=(k+n)%n;car.dataset.at=k;
    fs.forEach(function(f,j){f.classList.toggle('on',j===k);});
    var r=fs[k];if(r&&r.classList.contains('run')&&!r.dataset.asked)runner(r);
    var d=car.querySelector('.dots');d.replaceChildren();
    for(var j=0;n>1&&j<n;j++)d.appendChild(el('span',j===k?'on':null));
    car.querySelector('.cap').textContent=k?(fs[k].querySelector('figcaption')||{}).textContent||'':'';
    [].forEach.call(car.querySelectorAll('.flip'),function(b){b.hidden=n<2;});
  }
  function runner(f){
    f.dataset.asked=1;
    ctx.ref(f.dataset.name).then(function(t){var p=t&&t.default_photo,img=f.querySelector('img');
      if(p){img.src=String(p.medium_url||p.url||p.square_url).replace(/\/(square|small)\./,'/medium.');f.title=t.name+(p.attribution?'. Photo '+p.attribution:'');}
      else f.querySelector('figcaption').textContent='Runner-up: no reference photo';});
  }
  function flip(car,d){show(car,+car.dataset.at+d);}
  // the photo box: the observation's .ph inside, the arrows and dots over it
  function car(ph){
    var c=el('div','car'),tag=el('span','tag'),cap=el('span','cap'),dots=el('span','dots');
    c.dataset.at=0;tag.hidden=true;dots.setAttribute('aria-hidden','true');
    [['flip prv','Previous photo','M15 5l-7 7 7 7',-1],['flip nxt','Next photo','M9 5l7 7-7 7',1]].forEach(function(x){
      var b=el('button',x[0]);b.type='button';b.setAttribute('aria-label',x[1]);b.hidden=true;b.appendChild(svg(x[2]));
      b.onclick=function(e){e.stopPropagation();flip(c,x[3]);};c.appendChild(b);});
    c.prepend(ph);c.append(tag,cap,dots);
    var x0=null;  // a swipe flips, and its click does not open the panel
    c.addEventListener('pointerdown',function(e){x0=e.pointerType==='mouse'?null:e.clientX;});
    c.addEventListener('pointerup',function(e){if(x0==null)return;var dx=e.clientX-x0;x0=null;
      if(Math.abs(dx)>40){flip(c,dx<0?1:-1);c.dataset.swiped=1;setTimeout(function(){delete c.dataset.swiped;},50);}});
    c.addEventListener('click',function(e){if(c.dataset.swiped)e.stopPropagation();},true);
    return c;
  }
  // the card's lines and tag, from what its hidden title holds (call again when the title or the place changes)
  function face(li,place){
    var t=li.querySelector('.title'),c=li.querySelector('.car');if(!t||!c)return;
    var label=txt(t,'.name i'),look=txt(t,'.look i'),com=txt(t,'.com'),m=/(close call|fair margin|clear margin)$/.exec(txt(t,'.why')),
      run=t.querySelector('.why [data-la]'),old=t.querySelector('.face'),f=el('div','face'),hl=el('div','hl'),from=el('div','from');
    if(place!=null)li.dataset.place=place;place=li.dataset.place||'';
    hl.appendChild(look||label?I18N.nm(look||label):el('i',null,'Loading…'));if(look)hl.append('?');
    from.append(look?'from ':'',look?I18N.nm(label):I18N.names==='common'?'':com,(look||com&&I18N.names!=='common')&&place?' · ':'',place);
    f.append(hl,from);if(old)old.replaceWith(f);else t.append(f);
    var tg=c.querySelector('.tag');tg.hidden=!m;tg.textContent=m?m[1].charAt(0).toUpperCase()+m[1].slice(1):'';
    var r=c.querySelector('.run');
    if(run&&(!r||r.dataset.name!==run.textContent)){
      var fg=el('figure','run'),img=el('img');img.alt='Runner-up '+run.textContent+', reference photo';img.onerror=function(){img.removeAttribute('src');};
      fg.dataset.name=run.textContent;fg.append(img,el('figcaption',null,'Runner-up'));if(r)r.replaceWith(fg);else c.appendChild(fg);}
    else if(!run&&r)r.remove();
    show(c,Math.min(+c.dataset.at,frames(c).length-1));
  }
  // the hidden detail goes to the panel's slot while the panel shows the card, and back after; null takes it back
  function lend(li,slot){
    lent.forEach(function(x){x[0].replaceWith(x[1]);});lent=[];
    if(!li||!slot)return;
    [].forEach.call(li.querySelectorAll('.title .com,.title .sugg,.det'),function(n){var m=document.createComment('');n.before(m);lent.push([m,n]);slot.appendChild(n);});
  }
  function keys(li){
    li.addEventListener('keydown',function(e){var d={ArrowLeft:-1,ArrowRight:1}[e.key],c=li.querySelector('.car');
      if(e.target===li&&d&&c&&frames(c).length>1){e.preventDefault();flip(c,d);}});
  }
  return {car:car,face:face,lend:lend,keys:keys,paint:function(li){var c=li.querySelector('.car');if(c)show(c,+c.dataset.at);}};
};
})();
