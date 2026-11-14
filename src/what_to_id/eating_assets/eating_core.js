// What the Food web page reads: feeding observations (iNaturalist's Eating and Eaten by fields, foodweb-obs.json) and observations whose
// description or tags talk about food (foodweb-text.json) set against the metaweb (metaweb.json, pairs [predator, prey, p]).
// EatingCore.init(metaweb, obsFile, textFile) first; then the readers. A record is {o, pred, prey}: its taxon and what its field names,
// null when the field names no taxon (the prey of an Eating observation, the predator of an Eaten by one). Link out only.
var EatingCore=(function(){
'use strict';
function el(tag,cls,text){var e=document.createElement(tag);if(cls)e.className=cls;if(text!=null)e.textContent=text;return e;}
function genus(n){return n.split(' ')[0];}
// a: an observed name, m: a metaweb name (species or higher, here genus)
function is(a,m){return !!a&&!!m&&(a===m||m.indexOf(' ')<0&&genus(a)===m);}
// a: an observed name, m: a metaweb name or a clade it may lie in
function hit(a,m){return is(a,m)||within(a,m);}
// x: a name asked about, which may be a clade, m: a metaweb name
function cov(x,m){return is(x,m)||within(m,x);}
var M=null,names=null,ids=null,ALL=null,R={all:[],text:[]};
function pl(n,w){return n+' '+w+(n===1?'':'s');}
// common name by Latin name (the metaweb's, then the observations'), and Latin name by taxon id
function common(M,O){var c=new Map(Object.entries(M.common||{}));O.forEach(function(o){if(o.t[2])c.set(o.t[0],o.t[2]);});return c;}
function idsOf(O){var m=new Map();O.forEach(function(o){m.set(String(o.t[1]),o.t[0]);if(o.f)m.set(String(o.f[1]),o.f[0]);});return m;}
function label(n){return names.get(n)||n;}
// a hash value (Latin name, common name or taxon id) as a Latin name the data knows, or null
function find(v,pool){
  if(!v||v==='0')return null;
  if(ids.has(v)&&pool.has(ids.get(v)))return ids.get(v);
  if(pool.has(v))return v;
  var w=v.toLowerCase(),hit=null;pool.forEach(function(_,n){if(!hit&&(n.toLowerCase()===w||(names.get(n)||'').toLowerCase()===w))hit=n;});
  return hit;
}
// whether Latin name n is clade or lies below it, by the metaweb's parent table, else by genus
function within(n,clade){
  var g=genus(n);
  for(var k=0;n&&k<40;k++,n=M.parent&&M.parent[n])if(n===clade)return true;
  return clade.indexOf(' ')<0&&g===clade;
}
function roles(o){return o.k==='by'?{o:o,pred:o.f?o.f[0]:null,prey:o.t[0]}:{o:o,pred:o.t[0],prey:o.f?o.f[0]:null};}
// the animal is unresolved when unnamed or named above species
function open(x,side){var n=x[side];return !n||n.indexOf(' ')<0;}
function p(pred,prey){var b=0;M.pairs.forEach(function(q){if(cov(pred,q[0])&&cov(prey,q[1])&&q[2]>b)b=q[2];});return b;}
// photographed before: a feeding observation's field names the pair to species
function seen(pred,prey){return R.all.some(function(x){return x.pred&&x.prey&&hit(x.pred,pred)&&hit(x.prey,prey);});}
function preys(x){return M.pairs.filter(function(q){return cov(x,q[0]);}).sort(function(a,b){return b[2]-a[2];});}
function preds(y){return M.pairs.filter(function(q){return cov(y,q[1]);}).sort(function(a,b){return b[2]-a[2];});}
// the stand-in's p = 1 - 0.5^records as the records it counts
function words(p){return p<0.6?'one record':p<0.8?'two records':'three or more records';}
function init(metaweb,file,text){
  M=metaweb;var O=file.obs,T=(text&&text.obs)||[];R.all=O.map(roles);R.text=T.map(roles);names=common(M,O.concat(T));ids=idsOf(O.concat(T));ALL=new Map();
  M.pairs.forEach(function(x){ALL.set(x[0],1);ALL.set(x[1],1);});Object.keys(M.parent||{}).forEach(function(n){ALL.set(n,1);ALL.set(M.parent[n],1);});
  O.concat(T).forEach(function(o){ALL.set(o.t[0],1);if(o.f)ALL.set(o.f[0],1);});
}
// the page's "How this is made" note
function how(file,text){return 'Pairs: '+M.source+'. '+M.rule+'. Photographed before: '+pl(file.n.obs,'observation')+' with the Eating or Eaten by field (fetched '+file.fetched+'), '+file.n.named+' name a taxon in the field.'+
  (text?' Searched for food: '+pl(text.n,'observation')+' of a metaweb predator whose description or tags say eating, eats, ate, feeding, prey or caught, or are tagged predation, eating or feeding. Comments cannot be searched through the iNaturalist API, so they are not read.':' The description and tag search was not available.');}
return {init:init,el:el,pl:pl,label:label,find:find,hit:hit,cov:cov,within:within,open:open,p:p,seen:seen,preys:preys,preds:preds,words:words,how:how,
  R:R,M:function(){return M;},all:function(){return ALL;}};
})();
