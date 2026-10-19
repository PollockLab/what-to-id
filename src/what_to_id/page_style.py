"""Inline stylesheet and script for the identifier pages. Kept out of page.py for length.

Colours come from page_nav.CSS (light and dark); the names below alias them for these pages. One
system font stack, action green, uppercase section labels, pills and chips, literal arrows, no
gradients, no icons, no animation beyond border and brightness on hover.
"""

CSS = """
:root{--mut:var(--muted);--acc:var(--bar);--gd:#22c55e;--gold:#f0a000;--card:var(--panel);
--cink:var(--ink);--cmut:var(--muted);--line2:var(--line);--inset:var(--chip);--acc-ink:var(--ink);
--gd-ink:var(--bar);--gold-ink:var(--warn)}
*{box-sizing:border-box}
body{margin:0;background:var(--bg);color:var(--ink);font:15px/1.5 system-ui,-apple-system,
"Segoe UI",sans-serif}
main{max-width:64rem;margin:0 auto;padding:1.4rem 1rem 4rem}
h1{font-size:1.5rem;line-height:1.16;font-weight:700;margin:.2rem 0 .2rem}
h1 a{color:var(--acc);text-decoration:underline;text-decoration-thickness:1px;
text-underline-offset:3px}
h2{font-size:.8rem;font-weight:700;text-transform:uppercase;letter-spacing:.06em;color:var(--mut);
margin:2rem 0 .6rem}
h2 small{font-weight:500;text-transform:none;letter-spacing:0;margin-left:.5rem}
p.sub{margin:0 0 1.2rem;color:var(--mut)}
p.lede{font-size:1.02rem;color:var(--ink)}
p.crumbs{color:var(--mut);margin:0;font-size:.9rem}
p.crumbs a{color:var(--mut)}
p.legend{color:var(--mut);font-size:.9rem}
p.legend b{color:var(--ink);font-weight:600}
a{color:var(--acc)}
.how ol{padding-left:1.3rem;margin:.4rem 0}
.how li{margin:.3rem 0}
.how b{color:var(--ink)}
.how,.why{color:var(--mut)}
.cards{display:flex;gap:.8rem;flex-wrap:wrap;margin:1.4rem 0}
.card{flex:1 1 11rem;display:flex;flex-direction:column;gap:.1rem;padding:.9rem 1rem;
background:var(--card);border:1px solid var(--line);border-radius:12px;text-decoration:none;
color:var(--cink);box-shadow:var(--shadow);transition:border-color .12s}
.card:hover{border-color:var(--acc)}
.card b{font-size:1.25rem;color:var(--acc-ink);margin-bottom:.25rem}
.card b::after{content:" \\2192";color:var(--cmut)}
.card span{color:var(--cmut);font-size:.9rem}
table{border-collapse:collapse;width:100%;background:var(--card);color:var(--cink);
border:1px solid var(--line);border-radius:12px;overflow:hidden}
th,td{padding:.45rem .7rem;text-align:left;border-bottom:1px solid var(--line)}
thead th{background:var(--inset);font-weight:600;font-size:.85rem}
tbody th{font-weight:500}
td a{color:var(--gd-ink)}
tbody tr:last-child td,tbody tr:last-child th{border-bottom:0}
.groupnav{display:flex;flex-wrap:wrap;gap:.35rem;margin:1rem 0 .5rem}
.groupnav a{color:var(--ink);text-decoration:none;font-size:.85rem;font-weight:500;
padding:.25rem .7rem;border:1px solid var(--line);border-radius:14px;background:var(--panel);
transition:border-color .12s}
.groupnav a:hover{border-color:var(--acc)}
ul.batches{list-style:none;padding:0;margin:0;display:flex;flex-direction:column;gap:.45rem}
li.batch{display:grid;grid-template-columns:auto 5rem 1fr auto auto;gap:.8rem;align-items:center;
padding:.5rem .8rem;background:var(--card);color:var(--cink);border:1px solid var(--line);
border-radius:12px;transition:border-color .12s}
li.batch:hover{border-color:var(--acc)}
li.batch.is-done{opacity:.5}
li.batch.is-done .code{text-decoration:line-through}
.done{display:flex;align-items:center;gap:.3rem;color:var(--cmut);font-size:.85rem;
white-space:nowrap}
.done input{width:1.05rem;height:1.05rem;accent-color:var(--gd-ink)}
.code{font-weight:700;color:var(--acc-ink)}
.facts{color:var(--cmut);font-size:.88rem}
.thumbs{display:flex;gap:.25rem}
.thumbs img{width:44px;height:44px;object-fit:cover;border-radius:6px;background:var(--inset)}
.btn{display:inline-block;padding:.45rem .85rem;background:var(--gd);color:#062a12;
border-radius:8px;text-decoration:none;font-weight:700;white-space:nowrap;
transition:filter .12s}
.btn::after{content:" \\2192"}
.btn:hover{filter:brightness(1.08)}
.prov{margin-top:3rem;color:var(--mut);font-size:.82rem}
p.yourset{display:flex;align-items:center;gap:.7rem;margin:1.2rem 0 0;font-size:1.02rem}
p.yourset .swap{color:var(--mut);font-size:.88rem}
.card.is-mine{border-color:var(--gd);box-shadow:0 0 0 2px var(--gd),var(--shadow)}
.card.is-mine b::after{content:" \\2192 yours";color:var(--gd-ink);font-size:.8rem}
@media(max-width:44rem){li.batch{grid-template-columns:auto 1fr auto;grid-template-areas:
"done code btn" "facts facts facts" "thumbs thumbs thumbs"}
.done{grid-area:done}.code{grid-area:code}.facts{grid-area:facts}.thumbs{grid-area:thumbs}
.btn{grid-area:btn}}
""".strip()

JS = """
(function(){var K='what-to-id-done';var d={};try{d=JSON.parse(localStorage.getItem(K)||'{}')}
catch(e){}
document.querySelectorAll('input[data-batch]').forEach(function(b){var li=b.closest('li');
if(d[b.dataset.batch]){b.checked=true;li.classList.add('is-done')}
b.addEventListener('change',function(){if(b.checked){d[b.dataset.batch]=1}else{delete
d[b.dataset.batch]}li.classList.toggle('is-done',b.checked);
try{localStorage.setItem(K,JSON.stringify(d))}catch(e){}})})})();
(function(){var S='what-to-id-set';var cards=document.querySelectorAll('.card');var p=
document.querySelector('.yourset');if(!cards.length||!p)return;var mine=null;try{mine=
localStorage.getItem(S)}catch(e){}
function card(h){for(var i=0;i<cards.length;i++){if(cards[i].getAttribute('href')===h){
return cards[i]}}return null}
function show(h){var c=card(h);if(!c)return;cards.forEach(function(x){x.classList.remove(
'is-mine')});c.classList.add('is-mine');var a=p.querySelector('[data-yourset]');a.href=h;
a.textContent=c.querySelector('b').textContent;p.hidden=false}
function pick(skip){var pool=[];cards.forEach(function(c){var h=c.getAttribute('href');if(h!==
skip)pool.push(h)});var h=pool[Math.floor(Math.random()*pool.length)];try{localStorage.setItem(
S,h)}catch(e){}return h}
if(!mine||!card(mine))mine=pick(null);show(mine);
p.querySelector('[data-swap]').addEventListener('click',function(ev){ev.preventDefault();mine=
pick(mine);show(mine)})})();
""".strip()
