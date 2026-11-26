// The evidence search of the Food web page: shows the most promising BC observations for the question ten at a time, each with the
// pair it may show and why it was drawn, and the reader answers one question with four options (keys 1-4: not this predator, not eating,
// can't tell, eating), saved as the three checks (predator, prey, eating) the export has. Annotations,
// the annotations live in localStorage only (one key, read defensively); nothing goes to iNaturalist.
// The next ten come when the last card is answered, or on More photos.
// Rank = the pair's p in the metaweb x the evidence: 4 the field names the pair, 3 it names a coarse ancestor of one animal, 2 the
// description, tags or field text mention a candidate (common or Latin name), 1 they only talk about food (a text hit then names no prey) or the field is empty.
// A Visited flower of record (k visit, pollination page) whose plant is named is an insect card, no question: above species it lists the likely visitors of that plant inside
// the animal's taxon (narrow), a species at needs ID shows what GloBI has on the pair (confirm), a research-grade species is read-only evidence once a question names a side (seen).
// FoodLoop.init(E, onChange); FoodLoop.ask({x, y}) when the question changes; FoodLoop.state(pred, prey) is 'before', 'new' or ''.
var FoodLoop=(function(){
'use strict';
// the predator classes the filter offers: [iNaturalist class, button]; '' is all
var CLASSES=[['','All classes'],['Aves','Birds'],['Mammalia','Mammals'],['Reptilia','Reptiles'],['Amphibia','Amphibians'],['Insecta','Insects']],ANS=['yes','no','unsure'],
  // where a card comes from, the filter's buttons [key, button, title]; the model study (foodweb-vlm.json) wins over the other two
  SOURCES=[['study','Model study','Photos a vision model flagged as predation, prey not yet named'],['','All sources','Every source, the model study first'],['field','iNaturalist field','Observers filled in the Eating or Eaten by field'],['text','Description or tags','The description or tags talk about food']],
  // FOOD: the words foodweb_obs.SEARCHES looked for; the four options of a card's question and the three checks each one saves; only eating shows it (and asks which animal when the field did not name it)
  OPTS=[['Not this predator',['no','unsure','unsure']],['Not eating',['yes','yes','no']],['Can’t tell',['unsure','unsure','unsure']],['Eating',['yes','yes','yes']]],
  // a model-study card's blind six options [label, definition, the three checks, saved label, short button text], [P] the predator's name; the button shows the short text, its title the label and definition; only eating prey asks which animal
  STUDY=[['no [P] in the photo','or the animal shown is a different species, or you cannot tell whether it is a [P]',['no','unsure','unsure'],'no_predator','Predator not here'],['[P] is not eating','it is there, but resting, hunting, feeding on plants, or near other animals without contact',['yes','yes','no'],'not_eating','Not eating'],
    ['cannot tell','[P] is there, but the photo cannot show whether it is eating prey: too far, blurred, cropped or hidden, or the prey is only inferred (a bulge, a bloody mouth)',['unsure','unsure','unsure'],'cannot_tell','Cannot tell'],['[P] is eating prey','holding, carrying, killing or swallowing an animal; then name the prey',['yes','yes','yes'],'eating_prey','Eating'],
    ['eggs','[P] is eating or handling eggs',['yes','unsure','no'],'eggs','Eggs'],['carrion','[P] is eating a dead animal it did not kill: a carcass, roadkill, scraps',['yes','unsure','no'],'carrion','Carrion']],
  KEY='wtid-loop',FOOD=['eating','eats','ate','feeding','prey','caught','predation'],WEAK=['prey','caught'],OBS='https://www.inaturalist.org/observations/',API='https://api.inaturalist.org/v1/',TEN=10,W=(typeof EATING_CONFIG!=='undefined'&&EATING_CONFIG.words)||{},CAND=W.cand||'candidate observation',SHOW=8,$=function(id){return document.getElementById(id);};
// #record=<id> (a shared card): read before the page rewrites its hash, drawn first once it fits the question
var WANT=+((/(?:^|&)record=(\d+)(?:&|$)/.exec(location.hash.slice(1))||[])[1]||0);
// #part=i/n (one link per annotator, 1-based): this reader only draws observations with id % n = i-1, so no photo goes to two of them; kept in localStorage
var PART=/(?:^|&)part=(\d+)\/(\d+)(?:&|$)/.exec(location.hash.slice(1));
// the model study is the default source: Burak's set
var S={ann:{},cls:'',src:'study',part:null},H=null,E=null,Q={x:null,y:null},ITEMS=[],deck=[],cur=-1,change=function(){},TOK=new Map(),ready=false,booted=false;
function load(){
  try{var v=JSON.parse(localStorage.getItem(KEY));
    if(v&&typeof v==='object'){S.ann=v.ann&&typeof v.ann==='object'&&!Array.isArray(v.ann)?v.ann:{};
    S.by=v.by&&typeof v.by==='object'?v.by:{};var c=S.by[location.pathname];S.cls=CLASSES.some(function(k){return k[0]===c;})?c:'';if(SOURCES.some(function(c){return c[0]===v.src;}))S.src=v.src;S.part=v.part;}}catch(e){}
  if(PART)S.part=[+PART[1],+PART[2]];
  if(!(Array.isArray(S.part)&&S.part[0]>=1&&S.part[0]<=S.part[1]))S.part=null;
}
function source(r){return H&&H.obs[r.o.id]?'study':r.o.k==='text'?'text':'field';}
function study(c){return source(c.r)==='study';}
function mine(id){return !S.part||id%S.part[1]===S.part[0]-1;}
// food web and pollination share the marks, but each page keeps its own class filter
function save(){S.by=S.by||{};S.by[location.pathname]=S.cls;try{localStorage.setItem(KEY,JSON.stringify({ann:S.ann,src:S.src,part:S.part,by:S.by}));}catch(e){}}
function lc(s){return String(s||'').toLowerCase();}
// the words that name a prey in a text: its Latin and common name, and the common name's last word ("vole")
function tokens(n){
  if(!TOK.has(n)){var t=[lc(n)],c=lc(E.label(n));if(c!==t[0]){t.push(c);var w=c.split(/[ -]/).pop();if(w.length>=4&&t.indexOf(w)<0)t.push(w);}TOK.set(n,t);}
  return TOK.get(n);
}
function sg(w){return w.length<4?w:/ies$/.test(w)?w.slice(0,-3)+'y':/(ss|us|is)$/.test(w)?w:/(x|ch|sh|ss)es$/.test(w)?w.slice(0,-2):/s$/.test(w)?w.slice(0,-1):w;}  // tiny plural normalizer: s, es, ies to y
function word(text,tok){for(var i=text.indexOf(tok);i>=0;i=text.indexOf(tok,i+1))if((i===0||!/[a-z]/.test(text[i-1]))&&/^(e?s)?([^a-z]|$)/.test(text.slice(i+tok.length)))return true;return false;}  // a plural may end the word ("voles"), not "shrewd"
function mention(text,tok){var s=sg(tok);return word(text,tok)||word(text,s)||/y$/.test(s)&&word(text,s.slice(0,-1)+'ies');}  // "moths" in the metaweb, "a moth" in the text
// the observer's credit is not predation: "caught by @user", "photo by Sam", "caught on trail camera", and what follows an @user in its sentence
function credit(t){return t.replace(/\bcaught on (?:\w+ )?(?:cam\w*|video|film)\b/g,' ').replace(/\b(?:caught|photo(?:graph(?:ed)?)?|picture|image|taken|credit)\s+by\b(?:\s+@\w[\w.]*[^.!?\n]*|\s+\w+)?/g,' ').replace(/@\w[\w.]*[^.!?\n]*/g,' ');}
// group words to a clade name in the metaweb's parent table (hand-curated): named only when the predator has prey under that clade
var GROUP={shrimp:'Caridea',crab:'Brachyura',crayfish:'Astacidea',fish:'Actinopterygii',prickleback:'Stichaeidae',sculpin:'Cottidae',salmon:'Salmonidae',herring:'Clupeidae',insect:'Insecta',moth:'Lepidoptera',butterfly:'Lepidoptera',caterpillar:'Lepidoptera',dragonfly:'Odonata',beetle:'Coleoptera',fly:'Diptera',bee:'Anthophila',grasshopper:'Orthoptera',spider:'Araneae',snail:'Gastropoda',slug:'Gastropoda',clam:'Bivalvia',mussel:'Bivalvia',frog:'Anura',snake:'Serpentes',bird:'Aves',duck:'Anatidae',squirrel:'Sciuridae',rabbit:'Leporidae',damselfly:'Zygoptera','damsel fly':'Zygoptera',ladybug:'Coccinellidae',swallowtail:'Lepidoptera',meadowhawk:'Sympetrum',midge:'Diptera',stickleback:'Gasterosteidae','honey bee':'Apis mellifera'};
// the verbs of eating and killing: what follows the first one is the prey ("Damsel fly eating a moth"), unless it is the predator itself ("kills the darner")
var VERB=/\b(?:eat\w*|ate|feed\w*|fed|devour\w*|prey\w*|caught|catch\w*|captur\w*|kill\w*)\b/;
// what names no prey of the animal: "bird of prey", and its own predator ("caught by a bald eagle")
// a negated or failed catch ("could not see if it caught anything", "didn't catch", "missed") runs to its clause's end, and "no prey" names none
// a bee fly, robber fly, bee-eater or beewolf is no bee or fly prey; a parenthetical meal after another animal's name ("looking for ducks (eating dead salmon)") is that animal's
var NEG=/\b(?:\w+n['’]t|(?:could|did|does|do|was|were|is|are)nt|cannot|not|never|unable to|failed to|miss(?:ed|es)?|without)\b[^.!?\n,;]*|\bno (?:\w+ )?prey\b/g,
  COMPOUND=/\b(?:bee|robber)[ -]fl(?:y|ies)\b|\bbee[ -]?(?:eater|wolf)s?\b/g,
  OTHER=new RegExp('\\b(?:'+Object.keys(GROUP).join('|')+')s?\\b[^.!?\\n(]*\\((?:eating|feeding|eats)[^)]*\\)','g');
function quiet(t){return t.replace(NEG,' ').replace(COMPOUND,' ').replace(OTHER,' ').replace(/\bbirds? of prey\b/g,' ').replace(/[^.!?\n]*\b(?:mobb\w*|harass\w*|dive-?bomb\w*|diving at)\b[^.!?\n]*/g,' ').replace(/\b(?:caught|killed|eaten) by (?:an?|the) [^.!?\n]*/g,' ');}
// "X kills the <this animal>" after the verb: the animal is the victim
function victim(n,post){return tokens(n).some(function(t){return new RegExp('\\b(?:the|an?|this|that) '+t.replace(/[.*+?^${}()|[\]\\]/g,'\\$&')+'(?![a-z])').test(post);});}
// the first verb that names a prey: "caught" only before a determiner ("caught a shrimp", not "caught in a web", "caught my eye")
function verb(t){var re=new RegExp(VERB.source,'g'),m;while((m=re.exec(t))&&m[0]==='caught'&&!/^\s+(?:an?|the|some|its|his|her|their|this|that|one|two|three|several|another|\d+)\b/.test(t.slice(m.index+6)));return m;}
// every known animal's Latin and full common name (not its last word: "bee" is not a honey bee), for a prey the predator's metaweb row lacks
var EXT=null,EXTA=null;
function pool(){
  var a=E.all();
  if(EXTA!==a){EXTA=a;EXT=[];a.forEach(function(_,n){[lc(n),lc(E.label(n))].filter(function(t,i,l){return t.length>=4&&l.indexOf(t)===i;}).forEach(function(t){EXT.push([t,n,sg(t).replace(/y$/,"")]);});});}
  return EXT;
}
// the pairs one record may show, each with its evidence tier and the reason, as [{pred, prey, tier, why}]
function entries(r){
  if(r.o.k==='visit')return visiting(r);
  var o=r.o,eat=o.k!=='by',known=eat?r.pred:r.prey,named=eat?r.prey:r.pred,out=[];
  if(!known||known.indexOf(' ')<0)return out;
  var all=(eat?E.preys(known):E.preds(known)).map(function(q){return q[eat?1:0];}).filter(function(n,i,a){return a.indexOf(n)===i;}); // subspecies pairs repeat a partner
  function add(n,tier,why){out.push(eat?{pred:known,prey:n,tier:tier,why:why}:{pred:n,prey:known,tier:tier,why:why});}
  if(named&&!E.open(r,eat?'prey':'pred')){add(named,4,'The field names the pair');return out;}
  if(named){all.filter(function(n){return E.within(n,named);}).forEach(function(n){add(n,3,'The field names '+E.label(named)+', not a species');});return out;}
  // the description links the observer's own record of the prey: its taxon is the prey
  // not when it is the predator ("prey of", "killed by", "feeding on the <this animal>"), a chick fed, a flock, or a duplicate of the same genus
  // an animal on scat feeds on scat (not "on the dung fly"): what else the text names (the flies on it, the coyote that left it) is not its prey
  if(o.k==='text'&&/\bon\b[^.!?\n]{0,30}\b(?:scat|dung|droppings)\b(?! fl)/.test(lc(o.d)))return out;
  if(o.lk&&eat){var d=quiet(credit(lc(o.d))),m=verb(d);
    if(!/\bprey (?:of|to)\b|\b(?:killed|eaten|caught) by\b|\bfeeding (?:an?|the|its) (?!\w+ on\b)|\bflock|\baggregation/.test(lc(o.d))&&!(m&&victim(known,d.slice(m.index)))&&o.lk[0].split(' ')[0]!==known.split(' ')[0]){
      add(o.lk[0],3,'The description links the prey’s observation');return out;}}
  var src=[['Description',o.d],['Tags',(o.g||[]).join(' ')],['The field text',o.x]].filter(function(s){return s[1];});
  // a text hit whose only food word was the observer's credit ("caught by me") or the mobbers' sentence names no prey
  function fed(t){return VERB.test(t)||FOOD.some(function(w){return mention(t,w);});}
  var none=o.k==='text'&&src.some(function(s){return fed(lc(s[1]));})&&!src.some(function(s){return fed(credit(quiet(lc(s[1]))));});
  if(!none)src.forEach(function(s){var low=quiet(lc(s[1])),cl=credit(low),m=verb(cl),post=m?cl.slice(m.index+m[0].length):VERB.test(cl)?'':cl,how=s[0]+(s[0]==='Tags'?' mention ':' mentions ');
    // "X kills the <this animal>": the animal in the photo is the victim, so the text names no prey for it
    if(eat&&victim(known,post))return;
    all.forEach(function(n){var t=tokens(n).filter(function(k){return mention(low,k);})[0];
      if(t)add(n,2,how+'“'+t+'”');});
    if(!eat||out.length)return;
    // a prey the metaweb has no pair for: named all the same, it joins the network only once confirmed
    pool().forEach(function(x){if(post.indexOf(x[2])>=0&&mention(post,x[0])&&x[1]!==known&&!E.within(known,x[1])&&!out.some(function(e){return e.prey===x[1];}))add(x[1],2,how+'“'+x[0]+'”');});
    var g=Object.keys(GROUP).filter(function(w){return mention(post,w);});
    g.filter(function(w){return !g.some(function(v){return v!==w&&v.indexOf(w)>=0;});}).forEach(function(w){var c=GROUP[w];if(c!==known&&!out.some(function(e){return e.prey===c;}))add(c,2,how+'“'+w+'”');});});
  if(out.length)return out;
  // only a food word (the text search's): no prey is named, so the card asks about any prey, not the metaweb's likeliest
  // "caught" and "prey" alone name the victim as often ("caught in a web"): such a hit is no card
  if(o.k==='text'){var f=null,weak=false;src.forEach(function(s){var low=credit(quiet(lc(s[1])));FOOD.forEach(function(w){if(!f&&WEAK.indexOf(w)<0&&mention(low,w))f=s[0]+(s[0]==='Tags'?' mention ':' mentions ')+'“'+w+'”';});weak=weak||WEAK.some(function(w){return mention(lc(s[1]),w);});});
    if(!f&&weak)return out;add('',1,f||'Description or tags mention food');return out;}
  // the model's own guess (a taxon, else a group word) is the card's prey; with neither, it asks about any prey, not the metaweb's likeliest
  if(o.k==='model'){var h=H&&H.obs[o.id],l=h?[h.name].concat((h.prey||[]).map(function(q){return q[0];})):[],why='A vision model flagged feeding';
    var g=l.map(function(n){return String(n||'').replace(/ \(.*$/,'');}).filter(function(n){return E.all().has(n);})[0];
    if(!g)l.some(function(n){return Object.keys(GROUP).some(function(w){var c=GROUP[w];return mention(lc(n),w)&&all.some(function(m){return E.within(m,c);})&&(g=c);});});
    add(g||'',1,why);return out;}
  all.forEach(function(n){add(n,1,o.k==='text'?'Description or tags mention food':o.k==='model'?'A vision model flagged feeding':'The '+(eat?'Eating':'Eaten by')+' field '+(o.x?'has text, no taxon':'is empty'));});
  return out;
}
// an insect card's one pair; a species already confirmed, or a record with no plant named, has none
function visiting(r){
  var o=r.o,kind=r.pred.indexOf(' ')<0?'narrow':o.q==='needs_id'?'confirm':o.q==='research'?'seen':'';
  return r.prey&&kind?[{pred:r.pred,prey:r.prey,tier:4,why:'The field names the plant',kind:kind}]:[];
}
var KINDS=['narrow','confirm','seen'];
// the species GloBI has on the plant (a genus or species) inside the animal's taxon, most records first; records on several plants of a genus add up (1-0.5^n)
function likely(pred,plant){
  var m=new Map();
  E.preds(plant).forEach(function(q){if(q[0].indexOf(' ')>0&&E.within(q[0],pred))m.set(q[0],1-(1-(m.get(q[0])||0))*(1-q[2]));});
  return Array.from(m.keys()).sort(function(a,b){return m.get(b)-m.get(a)||(a<b?-1:1);}).map(function(n){return [n,m.get(n)];});
}
function taxon(n){var i=E.taxonId(n);return 'https://www.inaturalist.org/taxa/'+(i?i+'':'search?q='+encodeURIComponent(n));}
var QUALITY={needs_id:'Needs ID',research:'Research grade',casual:'Casual'};
// a signed-in viewer posts an ID from an insect card, as Identify's Agree does (identify_inat.js); no oauth config (Food web) or no client: links only
var IN=typeof IdentifyInat!=='undefined'&&EATING_CONFIG.oauth?IdentifyInat(EATING_CONFIG.oauth):null;
// the taxon's iNaturalist id: from the data, else its exact name in /v1/taxa (the metaweb carries no ids)
function taxonOf(n){var i=E.taxonId(n);return i?Promise.resolve(+i):fetch(API+'taxa?is_active=true&q='+encodeURIComponent(n)).then(function(r){if(!r.ok)throw new Error(r.status);return r.json();})
  .then(function(j){var t=(j.results||[]).filter(function(x){return x.name===n;})[0];if(!t)throw new Error('No taxon');return t.id;});}
function post(text,obs,n,label){
  var b=E.el('button','post',text);b.type='button';b.setAttribute('aria-label',label);
  b.onclick=function(){b.disabled=true;b.textContent='Posting…';
    taxonOf(n).then(function(t){return IN.identify(obs,t);}).then(function(){b.textContent='Posted';},function(){b.disabled=false;b.textContent='Not posted. Use iNaturalist';});};
  return b;
}
// the insect card's body: the likely visitors, each linking to its iNaturalist taxon page
function insect(c,li,f,d){
  var o=c.r.o,e=c.e,me=IN&&IN.on&&IN.user(),l=e.kind==='narrow'?likely(e.pred,e.prey):[],coarse=e.pred.indexOf(' ')<0,ol=E.el('ol','lk'),g=E.preds(e.prey).filter(function(q){return q[0]===e.pred;})[0];
  l.slice(0,SHOW).forEach(function(x){
    var i=E.el('li'),a=E.el('a',null,E.label(x[0]));a.href=taxon(x[0]);a.target='_blank';a.rel='noopener';
    i.append(a,E.el('em',null,(E.label(x[0])===x[0]?'':x[0]+' · ')+E.words(x[1])));if(me)i.append(post('Post ID',o.id,x[0],'Identify as '+E.label(x[0])+' on iNaturalist'));ol.append(i);});
  d.append(E.el('p','pair',E.label(e.pred)+' on '+E.label(e.prey)),
    E.el('p','evl',(QUALITY[o.q]||o.q)+' · '+E.pl(o.np||1,'photo')+(o.c?' · '+E.pl(o.c,'comment'):'')+' · '+(o.on||'Date unknown')+' · '+(o.at||'Place unknown')),
    e.kind==='seen'?E.el('p','ask','Already identified.'):e.kind==='confirm'?E.el('p','ask',g?'GloBI has '+E.words(g[2])+' of this species on '+E.label(e.prey)+', '+(g[3]||'visits')+'.':'GloBI has no record of this species on '+E.label(e.prey)+'.'):
    E.el('p','ask','Likely visitors of '+E.label(e.prey)+(coarse?', '+E.label(e.pred)+' only':'')+(l.length?' (most GloBI records first):':': none recorded in GloBI.')),ol);
  if(l.length>SHOW)d.append(E.el('p','evl','and '+(l.length-SHOW)+' more'));
  li.classList.toggle('done',e.kind==='seen');
  if(me&&e.kind==='confirm')d.append(post('Agree',o.id,e.pred,'Agree with '+E.label(e.pred)+' on iNaturalist'));
  else if(IN&&IN.on&&!me&&e.kind!=='seen'){var si=E.el('button','lnk','Sign in with iNaturalist'),sp=E.el('p','evl');si.type='button';si.onclick=IN.start;sp.append(si,' to post IDs from here');d.append(sp);}
  var go=E.el('a','open',e.kind==='confirm'&&!me?'Agree on iNaturalist':'Open on iNaturalist'),sh=E.el('button');go.href=OBS+o.id;go.target='_blank';go.rel='noopener';WtidCarry.share(sh,function(){return ['record='+o.id];});
  d.append(go,sh);li.append(f,d);li.onclick=function(){if(cur!==deck.indexOf(c))focus(deck.indexOf(c));};
  return li;
}
// the model's P(feeding) for the observation scales the rank (0.5, the neutral, when it has no hint)
function score(e,id){var h=H&&H.obs[id];return Math.max(E.p(e.pred,e.prey),0.1)*e.tier*(h?Math.max(h.p,0.1):0.5);}
function ok(e){return (e.kind!=='seen'||Q.x||Q.y)&&(!Q.x||E.hit(e.pred,Q.x))&&(!Q.y||E.hit(e.prey,Q.y))&&(!S.cls||E.inClass(e.pred,S.cls));}
// the records for the question not yet drawn or answered, best first, each with its best pair
function ranked(){
  var seen=new Set(deck.map(function(c){return c.r.o.id;}).concat(Object.keys(S.ann).map(Number))),out=[];
  ITEMS.forEach(function(it){
    if(seen.has(it.r.o.id)||!mine(it.r.o.id)||H&&S.src&&source(it.r)!==S.src)return;
    var b=null;it.es.forEach(function(e){if(ok(e)&&(!b||score(e,it.r.o.id)>score(b,it.r.o.id)))b=e;});
    if(b)out.push({r:it.r,e:b,s:score(b,it.r.o.id)});});
  var one=new Set();  // an observation with both fields is two records: its best one only
  // with the model's file: a pair the field already names comes last (iNaturalist has it), the model study's observations before the text search's
  // insect cards: narrow, then confirm, then the already identified
  var late=function(c){return H?(c.e.tier===4)*2-(source(c.r)==='study'):0;};
  return out.sort(function(a,b){return late(a)-late(b)||KINDS.indexOf(a.e.kind)-KINDS.indexOf(b.e.kind)||b.s-a.s||(a.r.o.on===b.r.o.on?a.r.o.id-b.r.o.id:b.r.o.on>a.r.o.on?1:-1);}).filter(function(c){return !one.has(c.r.o.id)&&one.add(c.r.o.id);});
}
function state(pred,prey){
  if(E.seen(pred,prey))return 'before';
  return Object.keys(S.ann).some(function(i){var a=S.ann[i];return a&&a.v==='yes'&&a.pred&&a.prey&&E.hit(a.pred,pred)&&E.hit(a.prey,prey);})?'new':'';
}
// the pairs the reader confirmed in this browser
function pairs(){var m=new Map();Object.keys(S.ann).forEach(function(i){var a=S.ann[i];if(a&&a.v==='yes'&&a.pred&&a.prey)m.set(a.pred+'|'+a.prey,[a.pred,a.prey]);});return Array.from(m.values());}
function photo(o,a){
  var img=E.el('img');img.src=o.ph;img.alt='Photo of '+E.label(o.t[0]);img.loading='lazy';
  img.onerror=function(){a.replaceChildren(E.el('span','nophoto','Photo not shown here'));};
  return img;
}
// an observation's photos (medium), fetched from iNaturalist on the first flip or zoom only; the card's one photo if that fails
function pics(c){
  var o=c.r.o;
  if(!c.pics)c.pics=fetch(API+'observations/'+o.id).then(function(r){if(!r.ok)throw new Error(r.status);return r.json();})
    .then(function(j){var l=((j.results||[])[0]||{}).photos||[];return l.length?l.map(function(p){return p.url.replace('/square.','/medium.');}):[o.ph];})
    .catch(function(){c.pics=null;return [o.ph];});
  return c.pics;
}
// photo i of the card (wraps), in the card and in the zoom view when it shows this card; the model's box is for the first photo only
function flip(c,i){
  return pics(c).then(function(l){
    c.pi=(i+l.length)%l.length;var f=c.li.querySelector('.ph'),a=f.querySelector('a'),img=a.querySelector('img')||a.appendChild(photo(c.r.o,a));
    img.src=l[c.pi];f.querySelector('.pn').textContent=(c.pi+1)+' / '+l.length;
    var b=a.querySelector('.pbox');if(b)b.hidden=c.pi>0;
    if(Z.c===c)Z.img.src=l[c.pi].replace('/medium.','/large.');
  });
}
// the zoom view: one modal dialog for the page (Escape closes it), the photo fit to the screen, a click or Enter shows it at full size
var Z={};
function zoom(c){
  if(!Z.d){
    Z.d=E.el('dialog','zoom');Z.img=E.el('img');Z.img.alt='';Z.img.tabIndex=0;var x=E.el('button','zx','Close'),p=E.el('button',null,'‹'),n=E.el('button',null,'›');
    x.type=p.type=n.type='button';p.setAttribute('aria-label','Previous photo');n.setAttribute('aria-label','Next photo');
    Z.img.title='Click for full size';Z.img.onclick=function(){Z.d.classList.toggle('full');};
    x.onclick=function(){Z.d.close();};p.onclick=function(){flip(Z.c,Z.c.pi-1);};n.onclick=function(){flip(Z.c,Z.c.pi+1);};
    Z.d.onclose=function(){var f=Z.c&&Z.c.li.querySelector('.zb');Z.c=null;if(f)f.focus();};
    Z.d.onkeydown=function(e){
      if(e.key==='ArrowLeft'||e.key==='ArrowRight'){e.preventDefault();flip(Z.c,Z.c.pi+(e.key==='ArrowLeft'?-1:1));}
      else if(e.key==='Enter'&&e.target===Z.img){e.preventDefault();Z.img.click();}};
    var bar=E.el('div','zbar');bar.append(p,n,x);Z.d.append(bar,Z.img);document.body.append(Z.d);
  }
  Z.c=c;Z.d.classList.remove('full');Z.img.alt='Photo of '+E.label(c.r.o.t[0])+', larger';Z.img.src=c.r.o.ph.replace('/medium.','/large.');
  Z.d.showModal();Z.img.focus();flip(c,c.pi||0);
}
// the vision-model hint of an observation (foodweb-vlm.json, absent is fine): the card's first line with a P(feeding) bar, and the prey box over the photo (0-1000 coords)
// its prey guess only when the model is the card's one source of prey (tier 1): the text or field's prey wins
function hint(o,a,d,own){
  var h=H&&H.obs[o.id];if(!h)return;
  var g=own?null:h.name||(h.prey[0]&&h.prey[0][0]),b=h.box;
  var l=E.el('p','evl vlm',(h.p>=0.9?'Very likely':h.p>=0.5?'Likely':'Unlikely')+' feeding'+(g?' · prey guess: '+E.label(g):'')),m=E.el('span','vbar'),f=E.el('i');
  l.title='Model P(feeding) '+h.p.toFixed(2);f.style.width=Math.round(h.p*100)+'%';m.append(f);l.prepend(m);d.append(l);
  if(b){var x=E.el('span','pbox');x.style.cssText='left:'+b[0]/10+'%;top:'+b[1]/10+'%;width:'+(b[2]-b[0])/10+'%;height:'+(b[3]-b[1])/10+'%';a.append(x);}
}
function pairText(e){return E.label(e.pred)+(e.tier===4?' eats ':' may be eating ')+(e.prey?E.label(e.prey):'something');}
function meter(){
  var r=ranked(),n=r.length,k=function(x){return r.filter(function(c){return c.e.kind===x;}).length;},m=n-k('confirm')-k('seen'),
    // the pollination page counts its insect cards apart: to narrow, to confirm, already identified
    got=[m||!k('confirm')&&!k('seen')?E.pl(m,CAND)+(k('narrow')?' to narrow':''):'',k('confirm')?k('confirm')+' to confirm':'',k('seen')?k('seen')+' already identified':''].filter(Boolean).join(', '),
    none=!n&&ready&&W.nophoto;  // nothing (more) to draw: no button, and say why
  // study mode has no draw button: the first photos come on their own, the rest after each answer
  if(H&&S.src==='study'&&ready&&n&&!deck.length)setTimeout(draw,0);
  $('draw').textContent=deck.length?'More photos':'Show photos';$('draw').disabled=!n||!ready;$('draw').hidden=!!none;
  $('cand').textContent=(S.part&&S.part[1]>1?'Your share: part '+S.part[0]+' of '+S.part[1]+'. ':'')+(H&&S.src==='study'&&ready?(n?E.pl(n,'photo')+' left to answer.':S.cls||Q.x||Q.y?'No photos left for this question. Open Food web question to widen it.':'All photos answered. Thank you.'):!ready?E.pl(n,CAND)+' so far. Searching descriptions and tags.':n?got+(deck.length||Q.x||Q.y?' for this question.':' across the whole web. Pick a species in the question to draw its photos, or show photos from all of them.'):none?(deck.length?(deck.length>1?'All '+E.pl(deck.length,'card')+' for this question are shown.':'The one card for this question is shown.'):Q.x&&Q.y?W.nophoto:W.noquestion):'No more observations for this question.');
}
// the three answers of a mark: a saved single mark (yes, no, unsure) is the same answer to all three
function steps(a){var t=a&&a.st;return Array.isArray(t)&&t.length===3&&t.every(function(x){return ANS.indexOf(x)>=0;})?t:a&&ANS.indexOf(a.v)>=0?[a.v,a.v,a.v]:[];}
// Shows it only when the animals are eating and neither photo-check said no; else Not visible if any said no, else Can't tell
function verdict(t){return t[2]==='yes'&&t[0]!=='no'&&t[1]!=='no'?'yes':t.indexOf('no')>=0?'no':'unsure';}
var STEPS=['Predator','Prey','Eating'],SAY={yes:'yes',no:'no',unsure:'can’t tell'};
function question(c){return study(c)?'Is '+E.label(c.e.pred)+' ('+c.e.pred+') eating something?':'Is '+E.label(c.e.pred)+' eating '+(c.e.prey?E.label(c.e.prey):'anything')+'?';}
function status(c){
  var a=S.ann[c.r.o.id],li=c.li,s=li.querySelector('.res'),busy=!li.querySelector('.which').hidden,got=busy?c.ans:steps(a);
  li.querySelector('.ask').textContent=a&&!busy?'':question(c);
  li.querySelector('.sum').textContent=got.map(function(x,i){return STEPS[i]+': '+SAY[x];}).join(' · ');
  s.textContent=!a||busy?'':a.v==='yes'?'Shows it'+(a.pred&&a.prey?': '+pairText({pred:a.pred,prey:a.prey,tier:4}).replace(' eats ',' eating '):''):a.lab==='eggs'?'Eggs':a.lab==='carrion'?'Carrion':a.v==='no'?'Not visible':'Can’t tell';
  li.classList.toggle('done',!!a);
  var h=li.querySelector('.hand'),y=!!a&&!busy&&a.v==='yes'&&!!a.pred&&!!a.prey;h.hidden=!y;li.querySelector('a.open').hidden=y;  // one link to the observation: the hand-off, else the plain one
  if(y){var by=c.r.o.k==='by',n=E.label(by?a.pred:a.prey),f=by?'Eaten by':'Eating';h.dataset.name=n;
    h.querySelector('a').textContent='Add '+f+' = '+n+' on iNaturalist';h.querySelector('.hint').textContent='On the observation, open Observation fields, pick '+f+', enter '+(by?'the predator':'the prey')+'.';h.querySelector('.cp').textContent='Copy';}
}
function next(){for(var k=1;k<=deck.length;k++){var i=(cur+k)%deck.length;if(!S.ann[deck[i].r.o.id]){focus(i);return;}}draw();}
function focus(i,quiet){
  cur=i;deck.forEach(function(c,j){c.li.classList.toggle('cur',j===i);});
  if(deck[i]&&!quiet)deck[i].li.scrollIntoView({block:'nearest',behavior:matchMedia('(prefers-reduced-motion:reduce)').matches?'auto':'smooth'});
}
function put(c,t,pred,prey){
  var a={v:verdict(t),st:t.slice(),on:new Date().toISOString().slice(0,10),ask:[c.e.pred,c.e.prey]};if(c.lab)a.lab=c.lab;if(pred){a.pred=pred;a.prey=prey;}
  S.ann[c.r.o.id]=a;save();status(c);change();next();
}
function copy(t,cs){(navigator.clipboard?navigator.clipboard.writeText(t):Promise.reject()).then(function(){cs.textContent='Copied';},function(){cs.textContent='Copy failed';});}
// the model's best prey guess for an observation among the names, or a species within the card's prey (its Latin name, "Latin (common)" read as Latin)
function guess(c,names){
  var h=H&&H.obs[c.r.o.id],l=h?[h.name].concat((h.prey||[]).map(function(q){return q[0];})):[];
  return l.map(function(n){return String(n||'').replace(/ \(.*$/,'');}).filter(function(n){return E.all().has(n)&&(names.indexOf(n)>=0||E.hit(n,c.e.prey));})[0]||null;
}
// Shows it on a card whose field does not name the pair: which animal, from the candidates (or any in the metaweb)
function which(c){
  var li=c.li,o=c.r.o,eat=o.k!=='by',known=eat?c.e.pred:c.e.prey,M=E.M(),box=li.querySelector('.which'),pick=null;
  if(!box.hidden)return;
  box.hidden=false;
  function fill(names){
    var g=eat&&!study(c)?guess(c,names):null,v=study(c)?null:g||(eat?c.e.prey:c.e.pred)||null,h=box.querySelector('.pk');if(g&&names.indexOf(g)<0)names=names.concat(g);
    h.replaceChildren(EatingPicker.create({id:'w'+o.id,ph:'Which '+(eat?'prey':'predator')+'?',value:v,names:names,obs:[],parent:M.parent,rank:M.rank,groups:M.groups,label:E.label,more:more,
      onPick:function(n){pick=n;value(n);}}));
    h.querySelector('input').setAttribute('aria-label','Which '+(eat?'prey':'predator')+' does the photo show?');pick=v;value(v);
  }
  // the iNaturalist field value for the animal picked, to copy before Confirm
  function value(n){box.querySelector('.ev').textContent=(eat?'Eating':'Eaten by')+' = '+E.label(n);box.querySelector('.cs').textContent='';}
  box.querySelector('.cp').onclick=function(){copy(E.label(pick),box.querySelector('.cs'));};
  function uniq(l){return Array.from(new Set(l));}
  fill(uniq((eat?E.preys(known):E.preds(known)).map(function(q){return q[eat?1:0];})));
  box.querySelector('.all').onclick=function(){fill(uniq(M.pairs.map(function(q){return q[eat?1:0];})));};
  box.querySelector('.ok').onclick=function(){if(pick){box.hidden=true;put(c,c.ans,eat?known:pick,eat?pick:known);}};
  box.querySelector('.ok').focus();
}
// any taxon, for an animal the metaweb lacks: iNaturalist's taxon search, the Latin name picked as the metaweb's are
function more(q){
  return fetch(API+'taxa/autocomplete?per_page=10&q='+encodeURIComponent(q)).then(function(r){if(!r.ok)throw new Error(r.status);return r.json();})
    .then(function(j){return (j.results||[]).filter(function(t){return t.name;}).map(function(t){E.add(t.name,t.preferred_common_name,t.id);return t.name;});});
}
// option i (0-3, a study card 0-5) of the card's question finishes the mark; Eating on a card whose field does not name the pair (a study card always) asks which animal
function answer(c,i){
  var sd=study(c),t=sd?STUDY[i][2]:OPTS[i][1],y=verdict(t)==='yes';c.ans=t;c.lab=sd?STUDY[i][3]:null;c.li.querySelector('.which').hidden=true;
  if(y&&(sd||c.e.tier!==4))return which(c),status(c);
  put(c,t,y?c.e.pred:undefined,c.e.prey);
}
function card(c){
  var o=c.r.o,li=E.el('li'),f=E.el('figure','ph'),a=E.el('a'),d=E.el('div'),b=E.el('p','mk');c.li=li;
  a.href=OBS+o.id;a.target='_blank';a.rel='noopener';a.append(photo(o,a));f.append(a);
  // flip through the observation's photos and zoom in, to tell the prey
  var zb=E.el('button','zb','Zoom');zb.type='button';zb.setAttribute('aria-label','Zoom photo');zb.onclick=function(){zoom(c);};
  var pn=E.el('span','pn');f.append(zb,pn);
  if((o.np||1)>1){pn.textContent='1 / '+o.np;[['‹','Previous photo',-1],['›','Next photo',1]].forEach(function(x){
    var k=E.el('button','pv',x[0]);k.type='button';k.setAttribute('aria-label',x[1]);k.onclick=function(){flip(c,(c.pi||0)+x[2]);};f.append(k);});}
  if(o.k==='visit')return insect(c,li,f,d);
  var sd=study(c),P=E.label(c.e.pred);  // a study card is blind: no hint, pair or why
  if(!sd)hint(o,a,d,c.e.tier>1);
  d.append.apply(d,(sd?[]:[E.el('p','pair',pairText(c.e)),E.el('p','evl','Why: '+c.e.why+'.')]).concat(E.el('p','evl',E.pl(o.np||1,'photo')+(o.c?' · '+E.pl(o.c,'comment'):'')+' · '+(o.on||'Date unknown')+' · '+(o.at||'Place unknown'))));
  (sd?STUDY:OPTS).forEach(function(x,i){
    var k=E.el('button',null,sd?'':x[0]+' ');k.type='button';
    if(sd){var df=x[0].replace(/\[P\]/g,P)+': '+x[1].replace(/\[P\]/g,P);k.title=df;k.setAttribute('aria-description',df);k.append(E.el('kbd',null,i+1),' ',E.el('b',null,x[4].replace(/\[P\]/g,P)));}else k.append(E.el('kbd',null,i+1));k.onclick=function(){focus(deck.indexOf(c));answer(c,i);};b.append(k);});
  var w=E.el('div','which'),pk=E.el('div','pk'),all=E.el('button','lnk all','Not in this list'),ok=E.el('button','ok','Confirm');
  w.hidden=true;all.type=ok.type='button';
  w.append(E.el('span','lab','Which '+(o.k==='by'?'predator':'prey')+'?'),pk,E.el('span','ev'),E.el('button','cp','Copy'),E.el('span','cs'),ok,all);
  w.querySelector('.cp').type='button';w.querySelector('.cs').setAttribute('aria-live','polite');
  // the hand-off: the page never writes to iNaturalist, so a confirmed mark sends the reader to add the field there
  var hd=E.el('div','hand'),ha=E.el('a'),cp=E.el('button','cp','Copy'),cs=E.el('span','cs');
  hd.hidden=true;ha.href=OBS+o.id;ha.target='_blank';ha.rel='noopener';cp.type='button';cs.setAttribute('aria-live','polite');
  cp.onclick=function(){copy(hd.dataset.name,cs);};
  hd.append(ha,cp,cs,E.el('p','hint evl'));
  var go=E.el('a','open','Open on iNaturalist');go.href=OBS+o.id;go.target='_blank';go.rel='noopener';
  var sh=E.el('button');WtidCarry.share(sh,function(){return ['record='+o.id];});
  d.append(E.el('p','ask'),b,w,E.el('p','res'),E.el('p','sum evl'),hd,go,sh);li.append(f,d);
  li.onclick=function(){if(cur!==deck.indexOf(c))focus(deck.indexOf(c));};
  status(c);return li;
}
function draw(auto){
  var r=ranked(),w=WANT?r.findIndex(function(c){return c.r.o.id===WANT;}):-1;if(w>0)r.unshift(r.splice(w,1)[0]);if(w>=0)WANT=0;
  var got=r.slice(0,TEN),ul=$('cards'),first=deck.length;
  got.forEach(function(c){deck.push(c);ul.append(card(c));});
  save();meter();if(got.length)focus(first,auto===true);
}
// asking starts over. The first ten are drawn when the question has a species (or on the first load, so the
// survey is not empty), once the food-word file has settled. Switching to the survey draws nothing: pick a species or press Show photos.
function ask(q){Q=q;deck=[];cur=-1;$('cards').replaceChildren();meter();if(!ready)return;var a=!!(q.x||q.y)||!booted;booted=true;if(a)draw(true);}
// what the network export needs: every mark (yes carries its pair, any mark the pair its card asked about), the pairs drawn, the photos shown
function marks(){return Object.keys(S.ann).filter(function(i){return S.ann[i];}).map(function(i){var a=S.ann[i];return {id:i,v:a.v,pred:a.pred,prey:a.prey,ask:a.ask};});}
function searched(pred,prey){
  var m=function(p){return p&&p[0]===pred&&p[1]===prey;};
  return deck.some(function(c){return c.e.pred===pred&&c.e.prey===prey;})||marks().some(function(a){return m(a.ask);});
}
function setSource(c){if(SOURCES.some(function(k){return k[0]===c;})){S.src=c;save();ask(Q);}}
function setClass(c){if(CLASSES.some(function(k){return k[0]===c;})){S.cls=c;save();ask(Q);}}
function shown(){return deck.length;}
function csv(){
  var q=function(v){return '"'+String(v==null?'':v).replace(/"/g,'""')+'"';};
  return ['observation_id,url,predator,prey,answer,date,is_predator,is_prey,is_eating,label'].concat(Object.keys(S.ann).map(function(i){var a=S.ann[i]||{};
    return [i,OBS+i,a.pred,a.prey,a.v,a.on].concat(steps(a).length?steps(a):['','',''],a.lab).map(q).join(',');})).join('\n')+'\n';
}
function exportCsv(){
  var u=URL.createObjectURL(new Blob([csv()],{type:'text/csv'})),a=E.el('a');a.href=u;a.download='food-web-annotations.csv';document.body.append(a);a.click();a.remove();setTimeout(function(){URL.revokeObjectURL(u);},1000);
}
function reload(){
  var ids=new Set(E.R.all.map(function(r){return r.o.id;})),mod=new Map(E.R.all.filter(function(r){return r.o.k==='model';}).map(function(r){return [r.o.id,r];})),
    fld=new Set(E.R.all.filter(function(r){return r.o.k!=='model';}).map(function(r){return r.o.id;}));
  // a field record also found by the text search is one card, the field's. A model record also found by it is one card too: the model's
  // (its P(feeding), its rank), but a prey the description names wins over the model's guess
  var merged=new Map();
  E.R.text.forEach(function(r){var l=r.o.lk;if(l)E.add(l[0],l[2],l[1]);});
  E.R.text.forEach(function(r){var m=mod.get(r.o.id);if(m&&!fld.has(r.o.id)){var es=entries(r).filter(function(e){return e.prey;});if(es.length)merged.set(m,es);}});
  ITEMS=E.R.all.concat(E.R.text.filter(function(r){return !ids.has(r.o.id);})).map(function(r){return {r:r,es:merged.get(r)||entries(r)};}).filter(function(it){return it.es.length;});
}
function init(core,onChange){
  E=core;change=onChange;load();
  reload();
  $('draw').onclick=function(){draw();};$('export').onclick=exportCsv;
  document.addEventListener('keydown',function(e){
    var t=e.target;if(e.ctrlKey||e.metaKey||e.altKey||/^(INPUT|TEXTAREA|SELECT)$/.test(t.tagName)||!deck.length||Z.c)return;
    if(e.key==='j'||e.key==='k'){e.preventDefault();focus(Math.max(0,Math.min(deck.length-1,(cur<0?0:cur)+(e.key==='j'?1:-1))));return;}
    var v=['1','2','3','4','5','6'].indexOf(e.key);if(v>=0&&cur>=0&&deck[cur].r.o.k!=='visit'&&(v<4||study(deck[cur]))){e.preventDefault();answer(deck[cur],v);}
  });
}
function go(){ready=true;}
function hints(v){H=v&&v.obs?v:null;}
return {likely:likely,hints:hints,init:init,reload:reload,go:go,ask:ask,state:state,pairs:pairs,marks:marks,searched:searched,shown:shown,csv:csv,CLASSES:CLASSES,SOURCES:SOURCES,src:function(){return S.src;},setSource:setSource,cls:function(){return S.cls;},setClass:setClass,steps:steps,verdict:verdict,entries:entries,S:S};
})();
