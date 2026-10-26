// The tree of life's model, apart from the page: the taxa table as a tree of record counts, what part
// of it is open, and where each shown node sits on the circle. Rows are pool-taxa.bin's [latin, common,
// iNaturalist id, rank, parent row, own records] (see taxonomy.py). Row n, past the table, is a root
// above every parentless row, so a tree with gaps still has one root; with one real root the unary
// rule below hides it.
// A taxon with one child and no records of its own is drawn merged into that child: the shown node is
// the lowest row of such a chain (lead), and its label names the whole chain. State S is
// {focus: shown root row, sel: selected row or -1, open: Map of open row -> pages of K children shown}.
(function(root,factory){
  var api=factory();
  if(typeof module!=='undefined'&&module.exports)module.exports=api;else root.TreeModel=api;
})(typeof globalThis!=='undefined'?globalThis:this,function(){
'use strict';
var K=24,GAP=0.35;
// iNaturalist's rank levels (Taxon::RANK_LEVELS); a rank it lacks sits half a step below its parent.
var LEVEL={stateofmatter:100,kingdom:70,subkingdom:67,phylum:60,subphylum:57,superclass:53,class:50,
  subclass:47,infraclass:45,subterclass:44,superorder:43,order:40,suborder:37,infraorder:35,parvorder:34.5,
  zoosection:34,zoosubsection:33.5,superfamily:33,epifamily:32,family:30,subfamily:27,supertribe:26,tribe:25,
  subtribe:24,genus:20,genushybrid:20,subgenus:15,section:13,subsection:12,complex:11,species:10,hybrid:10,
  subspecies:5,variety:5,form:5,infrahybrid:5};
// The rings: each major rank one step out from Life, the ranks between them in proportion.
var MAJOR=[[100,0],[70,1],[60,2],[50,3],[40,4],[30,5],[20,6],[10,7],[5,7.5]];
var RINGS=[['kingdom',1],['phylum',2],['class',3],['order',4],['family',5],['genus',6],['species',7]];
function step(l){
  if(!(l>=0))return NaN;if(l>=100)return 0;
  for(var i=1;i<MAJOR.length;i++)if(l>=MAJOR[i][0]){var a=MAJOR[i-1],b=MAJOR[i];
    return a[1]+(a[0]-l)/(a[0]-b[0])*(b[1]-a[1]);}
  return 7.5;
}
// groups: {iNaturalist id: life group name}, the map's groups that have a taxon. As on the map (iNaturalist's
// iconic taxa), each row takes the group of its nearest group ancestor, else REST. The group taxa hang from
// the root, so its children are the map's groups; a taxon they leave keeps the rest (ex: the group taxa
// taken out from under it). Children sort by records, most first. opt: names (the map's
// group names) and total (all records: those with no taxon, none, count in the totals of Life, which holds REST,
// but not in its own records; nr is the row that holds them).
var REST='Unknown',LIFE=48460;
function build(T,ranks,groups,opt){
  opt=opt||{};
  var n=T.length,N=n+1,par=new Int32Array(N),own=new Float64Array(N),tot=new Float64Array(N),
    st=new Float64Array(N),deep=new Float64Array(N),sp=new Float64Array(N),kids=[],row=new Map(),grp=[],ex=[],gr={},i,j;
  for(i=0;i<n;i++){var t=T[i];row.set(t[2],i);par[i]=t.length>4&&t[4]>=0?t[4]:n;own[i]=t[5]||0;
    st[i]=step(LEVEL[ranks[t[3]]]);}
  par[n]=-1;st[n]=0;row.set(0,n);
  for(i=0;i<n;i++)if(groups[T[i][2]]){for(j=par[i];j<n&&!groups[T[j][2]];j=par[j])(ex[j]=ex[j]||[]).push(T[i][2]);par[i]=n;}
  var nr=row.get(LIFE),none=opt.total?Math.max(0,opt.total-own.reduce(function(s,v){return s+v;},0)):0;if(nr==null)nr=n;
  for(j=nr;none&&j>=0;j=par[j])tot[j]+=none;
  for(i=0;i<N;i++){kids.push([]);if(own[i])for(j=i;j>=0;j=par[j])tot[j]+=own[i];}
  for(i=0;i<n;i++)if(tot[i]){kids[par[i]].push(i);
    if(T[i][3]>=0&&ranks[T[i][3]]==='species')for(j=i;j>=0;j=par[j])sp[j]++;}
  // a rank iNaturalist lacks: half a step below the nearest ranked ancestor
  for(i=0;i<n;i++)if(isNaN(st[i])){for(j=par[i];j>=0&&isNaN(st[j]);j=par[j]);st[i]=(j>=0?st[j]:0)+0.5;}
  for(i=0;i<N;i++){deep[i]=Math.max(deep[i],st[i]);if(tot[i])for(j=par[i];j>=0&&deep[j]<st[i];j=par[j])deep[j]=st[i];}
  for(i=0;i<N;i++)if(grp[i]===undefined){var path=[];
    for(j=i;j>=0&&grp[j]===undefined&&!(j<n&&groups[T[j][2]]);j=par[j])path.push(j);
    var g=j<0?REST:grp[j]!==undefined?grp[j]:groups[T[j][2]];if(j>=0)grp[j]=g;
    path.forEach(function(p){grp[p]=g;});}
  kids.forEach(function(k,p){k.sort(function(a,b){return tot[b]-tot[a]||a-b;});});
  kids[n].forEach(function(k){if(gr[grp[k]]==null)gr[grp[k]]=k;});
  return {T:T,ranks:ranks,n:n,root:n,par:par,own:own,tot:tot,st:st,deep:deep,sp:sp,kids:kids,row:row,grp:grp,groups:groups,
    ex:ex,gr:gr,names:opt.names||{},none:none,nr:nr,opt:opt};
}
// The tree less what the map leaves out: the groups named in names and the taxa with an iNaturalist id in ids
// (with everything below them), the same table with those records gone, so their nodes drop out and every count
// above them falls. Leaving out Unknown drops the records with no taxon too.
function without(M,names,ids){
  if(!names.length&&!(ids&&ids.length))return M;
  var out=new Set(ids),gone=0,T=M.T.map(function(t,i){
    var x=i;while(x<M.n&&!out.has(M.T[x][2]))x=M.par[x];
    if(x===M.n&&names.indexOf(M.grp[i])<0)return t;gone+=t[5]||0;return t.slice(0,5).concat([0]);}),
    o=Object.assign({},M.opt,{total:names.indexOf(REST)>=0?0:Math.max(0,(M.opt.total||0)-gone)});
  return build(T,M.ranks,M.groups,o);
}
// The tree of the records the map keeps: own[i] of them carry row i's taxon, total in all (those with no taxon too).
function recount(M,own,total){
  return build(M.T.map(function(t,i){return t.slice(0,5).concat([own[i]||0]);}),M.ranks,M.groups,
    Object.assign({},M.opt,{total:total}));
}
function id(M,r){return r===M.n?0:M.T[r][2];}
function name(M,r){return r===M.n?'Life':M.T[r][0];}
// A group's node takes the map's name for the group, "Other animals" for Animalia.
function common(M,r){var g=r<M.n&&M.par[r]===M.n&&M.names[M.grp[r]];
  return r===M.n?'':g?g.replace(/ \([^)]*\)$/,''):M.T[r][1];}
function rank(M,r){return r===M.n?'':M.ranks[M.T[r][3]]||'';}
// Whether row x holds records of its own, those with no taxon included.
function stop(M,x){return M.own[x]||x===M.nr&&M.none;}
function lead(M,x){for(;;){var k=M.kids[x];if(k.length!==1||stop(M,x))return x;x=k[0];}}
// The rows merged into shown node e, top first.
function chain(M,e){var out=[e];
  for(var p=M.par[e];p>=0&&p!==M.n&&M.kids[p].length===1&&!stop(M,p);p=M.par[p])out.unshift(p);
  return out;}
// The shown nodes above e, top first, down to (not including) e: the focus trail.
function crumbs(M,e){var out=[];for(var p=M.par[chain(M,e)[0]];p>=0;p=M.par[chain(M,p)[0]])
  if(p!==M.n||lead(M,p)===p)out.unshift(p);return out;}
// The selection the map and the photo space read for shown node e: a group's node is its group chip, any other
// taxon its pick less the groups taken out from under it (taxa=47120,-47158,-47119 for the other arthropods).
function pick(M,e){if(e<0||e===M.n)return '';if(M.par[chain(M,e)[0]]===M.n)return 'groups='+M.grp[e];
  return 'taxa='+[M.T[e][2]].concat((M.ex[e]||[]).map(function(i){return -i;})).join(',');}
// The row a map selection names: its first included taxon, else its one included group, else -1.
function find(M,s){var q={};String(s||'').split('&').forEach(function(t){var k=t.indexOf('=');
    if(k>0)q[t.slice(0,k)]=decodeURIComponent(t.slice(k+1));});
  var m=/(?:^|,)(\d+)/.exec(q.taxa||''),r=m?M.row.get(+m[1]):null;if(r!=null&&M.tot[r])return r;
  var g=(q.groups||'').split(',').filter(function(x){return x&&x[0]!=='-';});
  return g.length===1&&M.gr[g[0]]!=null?M.gr[g[0]]:-1;}
function within(M,a,t){for(var x=t;x>=0;x=M.par[x])if(x===a)return true;return false;}
// The shown tree from S.focus: each node {key, row, parent, depth, kids, open, tot, own, t (ring
// position), lo (deepest ring below), leaves}; a "more" node stands for the children past the open
// pages, row -1 and more = how many. all lists every node, parents first.
function view(M,S){
  var all=[];
  function node(e,parent,depth){
    var ks=M.kids[e],pages=S.open.get(e)||0,t=parent?Math.max(M.st[e],parent.t+GAP):M.st[e],
      nd={key:String(e),row:e,parent:parent,depth:depth,kids:[],open:pages>0&&ks.length>0,tot:M.tot[e],own:M.own[e],
        t:t,lo:ks.length?Math.max(M.deep[e],t+GAP):t,more:0};
    all.push(nd);
    if(nd.open){var lim=pages*K;
      ks.slice(0,lim).forEach(function(k){nd.kids.push(node(lead(M,k),nd,depth+1));});
      if(ks.length>lim){var rest=ks.slice(lim),m={key:'+'+e,row:-1,parent:nd,depth:depth+1,kids:[],open:false,
        tot:0,own:0,t:t+GAP,lo:t+GAP,more:rest.length,leaves:1};
        rest.forEach(function(k){m.tot+=M.tot[k];m.lo=Math.max(m.lo,M.deep[k]);});nd.kids.push(m);all.push(m);}}
    nd.leaves=nd.kids.length?nd.kids.reduce(function(s,k){return s+k.leaves;},0):1;
    return nd;}
  return {root:node(lead(M,S.focus),null,0),all:all};
}
// Opens e one level, or closes it.
function toggle(M,S,e){if(S.open.has(e))S.open.delete(e);else if(M.kids[e].length)S.open.set(e,1);}
function more(S,e){S.open.set(e,(S.open.get(e)||0)+1);}
// How deep an expand goes by default, per life group: the rank whose taxa it leaves closed. A click still
// opens any taxon down to species.
var DEPTH={Insecta:'order',Plantae:'family'},DEPTH_ELSE='family';
function cap(M,x){return step(LEVEL[DEPTH[M.grp[x]]||DEPTH_ELSE]);}
// Opens the subtrees under the shown nodes es (one row or a list) breadth first, biggest first, down to
// each group's depth (or all the way from a start already at or below it), while the shown leaves stay
// within budget. Returns whether it stopped short.
function expandBelow(M,S,es,budget){
  var L=view(M,S).root.leaves,q=[].concat(es).map(function(e){return [e,M.st[e]>=cap(M,e)];});
  while(q.length){var x=q[0][0],deep=q.shift()[1],ks=M.kids[x],pages=S.open.get(x);
    if(!ks.length||!pages&&!deep&&M.st[x]>=cap(M,x))continue;
    if(!pages){var d=Math.min(ks.length,K)+(ks.length>K?1:0)-1;if(L+d>budget)return true;
      S.open.set(x,pages=1);L+=d;}
    ks.slice(0,pages*K).forEach(function(k){q.push([lead(M,k),deep]);});}
  return false;
}
// Colours: each life group's sub-clades (the children of the group taxon) take alternating shades of the
// group colour, kept at 2:1 or more against both page backgrounds (#fbfbf9 light, #1a1a19 dark).
var TONES=[0,0.45,-0.35,0.25,-0.2,0.6,-0.5,0.12,-0.1];
function lum(c){return c.reduce(function(s,v,i){v/=255;v=v<=0.04045?v/12.92:Math.pow((v+0.055)/1.055,2.4);
  return s+v*[0.2126,0.7152,0.0722][i];},0);}
function contrast(a,b){var x=lum(a)+0.05,y=lum(b)+0.05;return Math.max(x,y)/Math.min(x,y);}
var BG=[[251,251,249],[26,26,25]];
// rgb mixed toward white (t>0) or black (t<0) by |t|, backed off until it reads on both pages.
function shade(rgb,t){
  for(var k=0;k<8&&t;k++,t/=2){var to=t>0?255:0,c=rgb.map(function(v){return Math.round(v+(to-v)*Math.abs(t));});
    if(BG.every(function(b){return contrast(c,b)>=2;}))return c;}
  return rgb.slice();
}
// Which tone row r takes: its sub-clade's index under its group's node, else 0.
function tone(M,r){
  for(var c=r,p=M.par[r];p>=0;c=p,p=M.par[p])if(p<M.n&&M.par[p]===M.n)return TONES[M.kids[p].indexOf(c)%TONES.length]||0;
  return 0;
}
// Opens the way from the focus to row t, paging through "more" as needed; a t outside the focus moves
// the focus to the root. Returns the shown node that holds t.
function reveal(M,S,t){
  var e=lead(M,t),f=lead(M,S.focus);
  if(e!==f&&!within(M,f,t))S.focus=f=lead(M,M.root);
  for(var c=t,p=M.par[t];p>=0&&e!==f;c=p,p=M.par[p]){
    if(lead(M,p)!==p)continue;
    var need=Math.floor(M.kids[p].indexOf(c)/K)+1;S.open.set(p,Math.max(S.open.get(p)||0,need));
    if(p===f)break;}
  return e;
}
// The opening view: the focus at the root, the life groups (rows gs) in sight and opened toward their
// depth while the view stays within HOME leaves.
var HOME=150;
function home(M,gs){
  var S={focus:lead(M,M.root),sel:-1,open:new Map()};
  gs.forEach(function(g){reveal(M,S,g);});
  if(!S.open.size)toggle(M,S,S.focus);
  expandBelow(M,S,gs.map(function(g){return lead(M,g);}).filter(function(e){return M.st[e]<cap(M,e);}),HOME);
  return S;
}
// Shares [a0, a1] among the shown nodes: siblings in proportion to the square root of their records,
// but each shown leaf at least min radians (less when the leaves would not fit).
function layout(V,a0,a1,min){
  min=Math.min(min,(a1-a0)/V.root.leaves);
  (function put(nd,a0,a1){nd.a0=a0;nd.a1=a1;nd.a=(a0+a1)/2;var ks=nd.kids;if(!ks.length)return;
    var s=a1-a0,req=0,w=0,a=a0;ks.forEach(function(k){req+=k.leaves*min;w+=Math.sqrt(k.tot);});
    ks.forEach(function(k,i){var d=req>=s?s*k.leaves*min/req:k.leaves*min+(s-req)*(w?Math.sqrt(k.tot)/w:1/ks.length);
      var b=i===ks.length-1?a1:a+d;put(k,a,b);a=b;});})(V.root,a0,a1);
  return V;
}
// The state as a hash, by iNaturalist id: focus=47170&sel=48250&open=47170,47169.2 (.2: two pages).
function write(M,S){
  var h=[],o=[];if(S.focus!==lead(M,M.root))h.push('focus='+id(M,S.focus));
  if(S.sel>=0)h.push('sel='+id(M,S.sel));
  S.open.forEach(function(p,r){o.push(id(M,r)+(p>1?'.'+p:''));});
  if(o.length)h.push('open='+o.join(','));
  return h.join('&');
}
// The state a hash names; without open=, the opening view with the selection revealed.
function read(M,hash,gs){
  var q={};String(hash||'').replace(/^#/,'').split('&').forEach(function(t){var k=t.indexOf('=');
    if(k>0)q[t.slice(0,k)]=decodeURIComponent(t.slice(k+1));});
  function rowOf(v){var r=M.row.get(+v);return r==null||!(r===M.n||M.tot[r])?-1:r;}
  var S=q.open==null?home(M,gs):{focus:lead(M,M.root),sel:-1,open:new Map()};
  if(q.open)q.open.split(',').forEach(function(t){var m=/^(\d+)(?:\.(\d+))?$/.exec(t),r=m?rowOf(m[1]):-1;
    if(r>=0&&M.kids[lead(M,r)].length)S.open.set(lead(M,r),Math.max(1,+(m[2]||1)));});
  var f=rowOf(q.focus);if(f>=0)S.focus=lead(M,f);
  var s=rowOf(q.sel);if(s>=0){S.sel=s;if(q.open==null)reveal(M,S,s);}
  return S;
}
return {K:K,REST:REST,LEVEL:LEVEL,RINGS:RINGS,DEPTH:DEPTH,TONES:TONES,BG:BG,cap:cap,shade:shade,tone:tone,contrast:contrast,step:step,build:build,without:without,recount:recount,id:id,name:name,common:common,rank:rank,lead:lead,pick:pick,find:find,
  chain:chain,crumbs:crumbs,within:within,view:view,toggle:toggle,more:more,expandBelow:expandBelow,reveal:reveal,
  home:home,layout:layout,write:write,read:read};
});
