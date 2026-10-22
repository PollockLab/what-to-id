// The map of life: the photo-space layout drawn as a political map. A grid over the layout gives each cell
// the clade whose smoothed record density is highest there. Zooming into a clade crops the view to the cells
// it holds and colours them by the rank below, in hues near the clade's own; the cells outside it stay clear,
// so the map of all life drawn under it shows through. Agreement and look-alike levels come from pool-lookalike.bin (per record, measured on the
// full BioCLIP neighbours), never from distances on this plot. Pure: arrays in, pixels and labels out.
(function(root,factory){
  var api=factory();
  if(typeof module!=='undefined'&&module.exports)module.exports=api;else root.LifeMap=api;
})(typeof globalThis!=='undefined'?globalThis:this,function(){
'use strict';
var RANKS=['kingdom','phylum','class','order','family'];
// The rank each view's regions are drawn at: the rank below the clade's, as far as the file measures agreement.
var FINE={life:'class',kingdom:'class',phylum:'class','class':'order',order:'family'};
var LONG=512,SIG=0.8,SIG_LOOK=1.5,K_LIFE=28,K_ZOOM=12;
// The coast follows a wider blur than the regions, islands under MIN_ISLAND cells join their surroundings, and
// every region, at life and at a zoom, is drawn at LIFE_TINT of its strength, so the points over it read and a
// zoom sits on the life map as a pastel like it (all at LONG cells).
var SIG_COAST=5,MIN_ISLAND=150,LIFE_TINT=.55;
var OTHER=[179,179,168],NODATA=[225,224,217];
var RAMP=[[205,226,251],[158,197,244],[109,167,236],[57,135,229],[37,106,191],[24,79,149],[13,54,107]];
var LEVELS=['same family','same order','same class','same phylum','same kingdom','other kingdom'];
var SEA=255,OUTSIDE=254,UNSET=253;  // cell codes past the region slots; UNSET is land with no record near

// Each taxa row's ancestor row at every rank in RANKS (itself at its own rank), or -1.
// T rows are [latin, common, inat_id, rank index into ranks, parent row, ...].
function ancestors(T,ranks){
  var R=T.length,A={},i;
  RANKS.forEach(function(k){A[k]=new Int32Array(R).fill(-2);});
  for(i=0;i<R;i++){
    var path=[],j=i;
    while(j>=0&&A.kingdom[j]===-2){path.push(j);j=T[j].length>4?T[j][4]:-1;}
    for(var p=path.length-1;p>=0;p--){
      var x=path[p],up=T[x].length>4?T[x][4]:-1,nm=ranks[T[x][3]];
      for(var r=0;r<RANKS.length;r++){var k=RANKS[r];A[k][x]=nm===k?x:up>=0?A[k][up]:-1;}
    }
  }
  return A;
}
function rankOf(T,ranks,row){return row<0?'life':ranks[T[row][3]]||'';}
function canZoom(T,ranks,row){return row>=0&&!!FINE[rankOf(T,ranks,row)];}

// pool-lookalike.bin, already gunzipped: plane A low nibble class, high nibble order agreement; plane B low
// nibble family agreement, high nibble look-alike level + 2. Agreement is in twelfths, 15 unknown.
function decodeLookalike(buf,n){
  var u=new Uint8Array(buf);
  if(u.length!==2*n)throw new Error('look-alike file holds '+u.length+' bytes, expected '+2*n);
  var c=new Uint8Array(n),o=new Uint8Array(n),f=new Uint8Array(n),lev=new Uint8Array(n);
  for(var i=0;i<n;i++){var a=u[i],b=u[n+i];c[i]=a&15;o[i]=a>>4;f[i]=b&15;lev[i]=b>>4;}
  return {n:n,agree:{'class':c,order:o,family:f},code:lev};
}
// A level code's look-alike level (0 same family .. 5 other kingdom, -1 undecidable, -2 none), or null.
function level(code){return code<=7?code-2:null;}

function kernel(s){
  var r=Math.max(1,Math.ceil(3*s)),k=new Float32Array(2*r+1),t=0,i;
  for(i=-r;i<=r;i++)t+=k[i+r]=Math.exp(-i*i/(2*s*s));
  for(i=0;i<k.length;i++)k[i]/=t;
  return k;
}
// Separable Gaussian blur of a W*H plane in place, zero outside the grid.
function blur(a,W,H,k,tmp){
  var r=(k.length-1)>>1,x,y,j,s,row;
  for(y=0;y<H;y++){row=y*W;
    for(x=0;x<W;x++){s=0;for(j=Math.max(-r,-x);j<=r&&x+j<W;j++)s+=a[row+x+j]*k[j+r];tmp[row+x]=s;}}
  for(y=0;y<H;y++)for(x=0;x<W;x++){
    s=0;for(j=Math.max(-r,-y);j<=r&&y+j<H;j++)s+=tmp[(y+j)*W+x]*k[j+r];a[y*W+x]=s;}
}
function grid(ext,long){
  var dx=ext[2]-ext[0]||1,dy=ext[3]-ext[1]||1,cs=Math.max(dx,dy)/long,
    W=Math.max(1,Math.round(dx/cs)),H=Math.max(1,Math.round(dy/cs));
  return {ext:ext,W:W,H:H,cs:cs,sx:W/dx,sy:H/dy};
}
function cellsOf(pos,n,g){
  var c=new Int32Array(n),x0=g.ext[0],y0=g.ext[1],W=g.W,H=g.H,sx=g.sx,sy=g.sy;
  for(var i=0;i<n;i++){
    var x=Math.floor((pos[2*i]-x0)*sx),y=Math.floor((pos[2*i+1]-y0)*sy);
    c[i]=x>=0&&x<W&&y>=0&&y<H?y*W+x:-1;
  }
  return c;
}
// Bins [lo,hi) of histogram h holding all but a share q of its mass at each end.
function qrange(h,q){
  var t=0,i,c=0,lo=0,hi=h.length-1;
  for(i=0;i<h.length;i++)t+=h[i];
  for(i=0;i<h.length;i++){c+=h[i];if(c>q*t){lo=i;break;}}
  for(c=0,i=h.length-1;i>=0;i--){c+=h[i];if(c>q*t){hi=i;break;}}
  return [lo,hi+1];
}
function padded(x0,x1,y0,y1,p){var dx=(x1-x0)*p,dy=(y1-y0)*p;return [x0-dx,y0-dy,x1+dx,y1+dy];}
// The box between the q and 1-q quantiles of all points, padded: a few strays do not shrink the map.
function lifeExtent(pos,n){
  var x0=1/0,y0=1/0,x1=-1/0,y1=-1/0,i,B=4096;
  for(i=0;i<n;i++){var x=pos[2*i],y=pos[2*i+1];if(x<x0)x0=x;if(x>x1)x1=x;if(y<y0)y0=y;if(y>y1)y1=y;}
  if(!(x1>x0))x1=x0+1;if(!(y1>y0))y1=y0+1;
  var hx=new Float64Array(B),hy=new Float64Array(B),sx=B/(x1-x0)*(1-1e-9),sy=B/(y1-y0)*(1-1e-9);
  for(i=0;i<n;i++){hx[Math.floor((pos[2*i]-x0)*sx)]++;hy[Math.floor((pos[2*i+1]-y0)*sy)]++;}
  var qx=qrange(hx,.002),qy=qrange(hy,.002);
  return padded(x0+qx[0]/sx,x0+qx[1]/sx,y0+qy[0]/sy,y0+qy[1]/sy,.02);
}
// Cells above half the 25th percentile of the non-empty ones: the land the map draws.
function landOf(tot){
  var v=[],i;for(i=0;i<tot.length;i++)if(tot[i]>0)v.push(tot[i]);
  if(!v.length)return new Uint8Array(tot.length);
  v.sort(function(a,b){return a-b;});
  var cut=.5*v[Math.floor(.25*(v.length-1))],land=new Uint8Array(tot.length);
  for(i=0;i<tot.length;i++)land[i]=tot[i]>cut?1:0;
  return land;
}
// Smooths a region raster in place: land with no record near takes the nearest region, islands under
// MIN_ISLAND cells join the region they border most, then a 3x3 majority rounds the boundaries. The sea and
// the cells outside a zoom's clade stay as they are.
function tidy(code,W,H,K,sc){
  var WH=W*H,q=new Int32Array(WH),cnt=new Int32Array(256),h=0,t=0,c,k,r,i;
  function nb(c,k){var x=c%W;return k===0?(x>0?c-1:-1):k===1?(x<W-1?c+1:-1):k===2?(c>=W?c-W:-1):c+W<WH?c+W:-1;}
  for(c=0;c<WH;c++)if(code[c]!==SEA&&code[c]!==UNSET)q[t++]=c;
  while(h<t){c=q[h++];for(k=0;k<4;k++){r=nb(c,k);if(r>=0&&code[r]===UNSET){code[r]=code[c];q[t++]=r;}}}
  for(c=0;c<WH;c++)if(code[c]===UNSET)code[c]=SEA;
  var cmp=new Uint8Array(WH),min=MIN_ISLAND*sc*sc;
  for(var pass=0,changed=1;pass<3&&changed;pass++){
    changed=0;cmp.fill(0);
    for(c=0;c<WH;c++){
      if(cmp[c]||code[c]>K)continue;
      var cd=code[c];h=t=0;q[t++]=c;cmp[c]=1;
      while(h<t){var p=q[h++];for(k=0;k<4;k++){r=nb(p,k);if(r<0)continue;
        if(code[r]===cd){if(!cmp[r]){cmp[r]=1;q[t++]=r;}}else if(code[r]<=K)cnt[code[r]]++;}}
      if(t<min){var best=-1;for(i=0;i<256;i++)if(cnt[i]&&(best<0||cnt[i]>cnt[best]))best=i;
        if(best>=0){for(i=0;i<t;i++)code[q[i]]=best;changed=1;}}
      cnt.fill(0);
    }
  }
  var src=code.slice(),v=[],x,y,dx,dy;
  for(y=0;y<H;y++)for(x=0;x<W;x++){
    c=y*W+x;if(src[c]>K)continue;
    v.length=0;
    for(dy=Math.max(0,y-1);dy<=Math.min(H-1,y+1);dy++)for(dx=Math.max(0,x-1);dx<=Math.min(W-1,x+1);dx++){
      var u=src[dy*W+dx];if(u<=K){if(!cnt[u])v.push(u);cnt[u]++;}}
    var m=src[c];for(i=0;i<v.length;i++)if(cnt[v[i]]>cnt[m])m=v[i];
    code[c]=m;for(i=0;i<v.length;i++)cnt[v[i]]=0;
  }
}
// The life-level grid, each point's cell, the smoothed density and the land of one point set: the half of a
// zoom's crop that does not depend on the clade, kept for the next zoom into the same points.
var LIFE=null;
function lifePass(pos,n){
  if(LIFE&&LIFE.pos===pos&&LIFE.n===n)return LIFE;
  var g=grid(lifeExtent(pos,n),LONG),WH=g.W*g.H,cell=cellsOf(pos,n,g),tot=new Float32Array(WH),i;
  for(i=0;i<n;i++)if(cell[i]>=0)tot[cell[i]]++;
  blur(tot,g.W,g.H,kernel(SIG),new Float32Array(WH));
  return LIFE={pos:pos,n:n,g:g,cell:cell,tot:tot,land:landOf(tot)};
}
// The zoom's crop: the connected patches of life-level cells where the clade holds over half the smoothed
// density, those with at least PATCH of the largest one's records (a big clade also holds scattered small
// patches, whose box would be the whole map), boxed by the quantiles of its records there. A clade with no such cells gets the box of all its records.
var PATCH=.25;
function territoryExtent(o,inTax){
  var P=lifePass(o.pos,o.n),g=P.g,W=g.W,WH=W*g.H,cell=P.cell,tot=P.tot,land=P.land,cz=new Float32Array(WH),raw,i;
  for(i=0;i<o.n;i++){var c=cell[i];if(c>=0&&inTax[o.tax[i]])cz[c]++;}
  raw=cz.slice();blur(cz,W,g.H,kernel(SIG),new Float32Array(WH));
  var own=new Int32Array(WH),q=new Int32Array(WH),wt=[0],bw=0,id=0,k;
  for(i=0;i<WH;i++)own[i]=land[i]&&cz[i]>.5*tot[i]?-1:0;
  for(i=0;i<WH;i++){
    if(own[i]!==-1)continue;
    var h=0,t=0,w=0;own[i]=++id;q[t++]=i;
    while(h<t){var p=q[h++],x=p%W;w+=raw[p];
      for(k=0;k<4;k++){var r=k===0?(x>0?p-1:-1):k===1?(x<W-1?p+1:-1):k===2?p-W:p+W;
        if(r>=0&&r<WH&&own[r]===-1){own[r]=id;q[t++]=r;}}}
    wt.push(w);bw=Math.max(bw,w);
  }
  var hx=new Float64Array(W),hy=new Float64Array(g.H),m=0;
  for(var pass=0;pass<2&&!m;pass++)for(i=0;i<WH;i++){
    if(!raw[i]||(!pass&&!(wt[own[i]]>=PATCH*bw)))continue;
    hx[i%W]+=raw[i];hy[Math.floor(i/W)]+=raw[i];m+=raw[i];}
  if(!m)return null;
  var qx=qrange(hx,.001),qy=qrange(hy,.001),e=g.ext;
  return padded(e[0]+qx[0]/g.sx,e[0]+qx[1]/g.sx,e[1]+qy[0]/g.sy,e[1]+qy[1]/g.sy,.04);
}
function mix(c,w,t){return [c[0]*(1-t)+w[0]*t,c[1]*(1-t)+w[1]*t,c[2]*(1-t)+w[2]*t];}
var WHITE=[255,255,255];
function ramp(t){
  t=Math.max(0,Math.min(1,t))*(RAMP.length-1);var i=Math.min(RAMP.length-2,Math.floor(t));
  return mix(RAMP[i],RAMP[i+1],t-i);
}

// Sibling s of a clade drawn in rgb: a hue within HUE degrees of the clade's, then lighter or darker, so a zoom
// keeps its parent's colour family and siblings still tell apart.
var HUE=28,HUES=[0,-1,1,-.5,.5],LIGHT=[0,.12,-.12];
function hsl(c){
  var r=c[0]/255,g=c[1]/255,b=c[2]/255,mx=Math.max(r,g,b),mn=Math.min(r,g,b),l=(mx+mn)/2,d=mx-mn,h=0;
  if(d)h=60*(mx===r?(g-b)/d+(g<b?6:0):mx===g?(b-r)/d+2:(r-g)/d+4);
  return [h,d?d/(1-Math.abs(2*l-1)):0,l];
}
function rgb(h,s,l){
  var c=(1-Math.abs(2*l-1))*s,x=c*(1-Math.abs(h/60%2-1)),m=l-c/2,k=Math.floor(h/60)%6,
    v=[[c,x,0],[x,c,0],[0,c,x],[0,x,c],[x,0,c],[c,0,x]][k];
  return [255*(v[0]+m),255*(v[1]+m),255*(v[2]+m)];
}
function shade(c,s){
  var p=hsl(c);
  return rgb((p[0]+HUE*HUES[s%5]+360)%360,p[1],Math.max(.2,Math.min(.8,p[2]+LIGHT[Math.floor(s/5)%3])));
}
// Per taxa row (65535 unknown), whether it lies in clade (-1: everything).
function within(T,A,ranks,clade){
  var R=T.length,zr=rankOf(T,ranks,clade),a=new Uint8Array(65536);
  for(var t=0;t<65536;t++)a[t]=clade<0||(t<R&&A[zr][t]===clade)?1:0;
  return a;
}
// The box a zoom into o.clade crops to (o as for build), or null.
function extent(o){return territoryExtent(o,within(o.T,o.A,o.ranks,o.clade));}
// The region at layout point (x,y): on the deepest zoomed map of Z (a map, or maps from shallow to deep) that has
// its clade there, else on the life map; with the clade it is the region of (the map's own clade for its "other"
// region), or null over the sea.
function region(life,Z,x,y){
  for(var zs=[].concat(Z||[]),i=zs.length-1,h;i>=0;i--){
    h=hit(zs[i],x,y);
    if(h&&h.slot>=0){var r=zs[i].slots[h.slot].row;return {map:zs[i],hit:h,row:r>=0?r:zs[i].clade};}
  }
  h=hit(life,x,y);
  return h&&h.slot>=0?{map:life,hit:h,row:life.slots[h.slot].row}:null;
}
// The clade view box b looks at: -1 (all life) while it holds over LIFE_VIEW of the life map's land, else the
// deepest clade a map can be drawn for whose regions hold over FILL of the land of a grid of samples over b, read
// as region reads Z. Z holds the focused clade's ancestors' maps too: its own map keeps only the cells it holds a
// majority of, where its parent's gave it every cell it led, so on its own map its share would drop once in focus.
var LIFE_VIEW=.6,FILL=.5,SAMPLES=24;
function focus(life,Z,A,T,ranks,b){
  var W=life.W,e=life.ext,x0=Math.max(0,Math.floor((b[0]-e[0])*life.sx)),x1=Math.min(W,Math.ceil((b[2]-e[0])*life.sx)),
    y0=Math.max(0,Math.floor((b[1]-e[1])*life.sy)),y1=Math.min(life.H,Math.ceil((b[3]-e[1])*life.sy)),land=0,x,y,i,j;
  for(y=y0;y<y1;y++)for(x=x0;x<x1;x++)if(life.code[y*W+x]!==SEA)land++;
  if(land>LIFE_VIEW*life.nLand)return -1;
  var n=0,cnt={};RANKS.forEach(function(k){cnt[k]=new Map();});
  for(i=0;i<SAMPLES;i++)for(j=0;j<SAMPLES;j++){
    var u=region(life,Z,b[0]+(i+.5)/SAMPLES*(b[2]-b[0]),b[1]+(j+.5)/SAMPLES*(b[3]-b[1]));
    if(!u)continue;
    n++;if(u.row<0)continue;
    RANKS.forEach(function(k){var a=A[k][u.row];if(a>=0)cnt[k].set(a,(cnt[k].get(a)||0)+1);});
  }
  for(var q=RANKS.length-1;q>=0;q--){
    if(!FINE[RANKS[q]])continue;
    var best=-1,bn=0;cnt[RANKS[q]].forEach(function(v,r){if(v>bn){bn=v;best=r;}});
    if(bn>FILL*n)return best;
  }
  return -1;
}

// o: {pos (x,y per point), n, tax (taxa row per point, 65535 unknown), grp (group per point), groups (count),
// color(g) -> rgb, T, ranks, A (ancestors), clade (taxa row, -1 for the whole of life), look (decodeLookalike,
// or null), src (each point's row in the look-alike file), long (cells on the long side, default LONG), rgb (the
// clade's colour, or null), known(row) -> a class's colour on the map of life, or null}.
function build(o){
  // sc: cells per LONG cell; every length or count in cells scales with it, so a finer grid draws the same map
  var long=o.long||LONG,sc=long/LONG,T=o.T,R=T.length,A=o.A,clade=o.clade==null?-1:o.clade,zr=rankOf(T,o.ranks,clade),fine=FINE[zr];
  if(!fine)throw new Error('cannot zoom into a '+zr);
  var NT=65536,inTax=within(T,A,o.ranks,clade),fineOf=new Int32Array(NT).fill(-1),t,i;
  for(t=0;t<R;t++)fineOf[t]=A[fine][t];
  var ext=clade<0?lifeExtent(o.pos,o.n):territoryExtent(o,inTax);
  if(!ext)return null;
  var g=grid(ext,long),W=g.W,H=g.H,WH=W*H,cell=cellsOf(o.pos,o.n,g);
  // the slots: the K commonest fine-rank clades inside the view, then one for everything else
  var tc=new Float64Array(NT),byRow=new Map();
  for(i=0;i<o.n;i++)if(cell[i]>=0)tc[o.tax[i]]++;
  for(t=0;t<NT;t++)if(tc[t]&&inTax[t]&&fineOf[t]>=0)byRow.set(fineOf[t],(byRow.get(fineOf[t])||0)+tc[t]);
  var rows=Array.from(byRow.keys()).sort(function(a,b){return byRow.get(b)-byRow.get(a)||a-b;})
    .slice(0,clade<0?K_LIFE:K_ZOOM),K=rows.length,slotOf=new Int16Array(NT).fill(-1),idx=new Map();
  rows.forEach(function(r,s){idx.set(r,s);});
  for(t=0;t<NT;t++)if(inTax[t])slotOf[t]=idx.has(fineOf[t])?idx.get(fineOf[t]):K;
  var S=new Float32Array((K+1)*WH),tot=new Float32Array(WH),G=o.groups||1,sGrp=new Float64Array((K+1)*G),
    sN=new Float64Array(K+1),sA=new Float64Array(K+1),sAc=new Float64Array(K+1),L=o.look,src=o.src,
    agr=L?L.agree[fine]:null,lc=L?L.code:null,aS=new Float32Array(WH),aC=new Float32Array(WH),
    vS=new Float32Array(WH),vC=new Float32Array(WH),LH=L?new Uint16Array(6*WH):null;
  for(i=0;i<o.n;i++){
    var c=cell[i];if(c<0)continue;
    tot[c]++;var s=slotOf[o.tax[i]];if(s<0)continue;
    S[s*WH+c]++;sN[s]++;if(o.grp)sGrp[s*G+o.grp[i]]++;
    if(!L)continue;
    var r=src?src[i]:i,a=agr[r],v=lc[r];
    if(a<=12){aS[c]+=a/12;aC[c]++;sA[s]+=a/12;sAc[s]++;}
    if(v>=2&&v<=7){vS[c]+=v-2;vC[c]++;if(LH[(v-2)*WH+c]<65535)LH[(v-2)*WH+c]++;}
  }
  var raw=tot.slice(),tmp=new Float32Array(WH),k=kernel(SIG*sc),kl=kernel(SIG_LOOK*sc),few=.05/(sc*sc);
  for(s=0;s<=K;s++)blur(S.subarray(s*WH,(s+1)*WH),W,H,k,tmp);
  blur(tot,W,H,k,tmp);
  if(L){blur(aS,W,H,k,tmp);blur(aC,W,H,k,tmp);blur(vS,W,H,kl,tmp);blur(vC,W,H,kl,tmp);}
  var coast=raw.slice();blur(coast,W,H,kernel(SIG_COAST*sc),tmp);
  var land=landOf(coast),code=new Uint8Array(WH),den=new Float32Array(WH),nLand=0;
  for(c=0;c<WH;c++){
    if(!land[c]){code[c]=SEA;continue;}
    nLand++;
    if(!(tot[c]>0)){code[c]=UNSET;continue;}
    var best=0,mx=-1,sum=0;
    for(s=0;s<=K;s++){var d=S[s*WH+c];sum+=d;if(d>mx){mx=d;best=s;}}
    if(clade>=0&&!(sum>.5*tot[c])){code[c]=OUTSIDE;continue;}
    code[c]=best;den[c]=clade<0?tot[c]:sum;
  }
  tidy(code,W,H,K,sc);
  // colours: a class keeps the colour the map of life gave it (o.known), else its group's colour, siblings in
  // one group paler; an order or family is a shade of its clade's colour (o.rgb, else its commonest group's)
  function major(s0,s1){var bg=0,q,s,t=new Float64Array(G);
    for(s=s0;s<s1;s++)for(q=0;q<G;q++)t[q]+=sGrp[s*G+q];
    for(q=1;q<G;q++)if(t[q]>t[bg])bg=q;return bg;}
  var seen={},base=fine==='class'?null:o.rgb||o.color(major(0,K+1)),slots=rows.map(function(row,s){
    var rgb=base?shade(base,s):o.known&&o.known(row);
    if(!rgb){var bg=major(s,s+1),sib=seen[bg]=(seen[bg]===undefined?-1:seen[bg])+1;rgb=mix(o.color(bg),WHITE,.28*(sib%3));}
    return {row:row,rgb:rgb,n:sN[s],agree:sAc[s]?sA[s]/sAc[s]:null};
  });
  slots.push({row:-1,rgb:o.rgb||base?mix(o.rgb||base,WHITE,.55):OTHER,n:sN[K],agree:null});
  var kOf=slots.map(function(sl){return sl.row>=0?A.kingdom[sl.row]:-1;}),
    img=new Uint8ClampedArray(4*WH),look=L?new Uint8ClampedArray(4*WH):null;
  function put(a,c,rgb,al){var p=4*((H-1-Math.floor(c/W))*W+c%W);a[p]=rgb[0];a[p+1]=rgb[1];a[p+2]=rgb[2];a[p+3]=al;}
  for(c=0;c<WH;c++){
    var cd=code[c];
    if(cd===SEA||cd===OUTSIDE)continue;
    // contested cells, and cells whose records' photo neighbours mostly lie outside their clade, read paler
    var dom=den[c]>0?S[cd*WH+c]/den[c]:1,f=.35+.65*dom*(aC[c]>few?Math.min(1,aS[c]/aC[c]):1);
    f*=LIFE_TINT;
    // a zoom fades out where its clade's share falls to the half it needs, so its edge blends into the life map
    var al=clade<0?255:255*Math.min(1,Math.max(0,(den[c]/tot[c]-.5)/.25));
    put(img,c,mix(slots[cd].rgb,WHITE,1-f),al);
    if(look)put(look,c,vC[c]>few?ramp(vS[c]/vC[c]/3):NODATA,al);
  }
  borders(img,code,W,H,clade<0?kOf:null);
  return {ext:ext,W:W,H:H,cs:g.cs,sc:sc,sx:g.sx,sy:g.sy,clade:clade,rank:zr,fine:fine,code:code,raw:raw,levels:LH,nLand:nLand,
    slots:slots,K:K,image:img,look:look,labels:labels(code,raw,W,H,g,slots,T,K,clade<0?kOf:null,nLand,sc)};
}
// Thin lines between regions, a darker coast, thick black between kingdoms (kOf given, at life only).
function borders(img,code,W,H,kOf){
  var e=new Uint8Array(W*H),c,x,y;
  function mark(a,b){
    var ca=code[a],cb=code[b];if(ca===cb)return;
    if(ca===SEA||cb===SEA){e[ca===SEA?b:a]|=2;return;}
    e[a]|=1;
    if(kOf&&ca<kOf.length&&cb<kOf.length&&kOf[ca]>=0&&kOf[cb]>=0&&kOf[ca]!==kOf[cb]){e[a]|=4;e[b]|=4;}
  }
  for(y=0;y<H;y++)for(x=0;x<W;x++){c=y*W+x;if(x+1<W)mark(c,c+1);if(y+1<H)mark(c,c+W);}
  for(c=0;c<W*H;c++){
    if(!e[c])continue;
    var p=4*((H-1-Math.floor(c/W))*W+c%W),ink=e[c]&4?[0,0,0,1]:e[c]&2?[77,77,77,.8]:[64,64,64,.55];
    for(var j=0;j<3;j++)img[p+j]=img[p+j]*(1-ink[3])+ink[j]*ink[3];
  }
}
// A label at the pole of inaccessibility of each region's largest island, an italic repeat on the largest other
// island holding a third of the region's records (raw, per cell), and at life each kingdom's share of the map
// around the edge. Sizes are in layout units.
function labels(code,raw,W,H,g,slots,T,K,kOf,nLand,sc){
  var WH=W*H,d=new Float32Array(WH),c,x,y,INF=1e9,R2=Math.SQRT2;
  for(c=0;c<WH;c++){
    if(code[c]>K){d[c]=0;continue;}
    x=c%W;y=(c-x)/W;
    d[c]=x===0||y===0||x===W-1||y===H-1||code[c-1]!==code[c]||code[c+1]!==code[c]||code[c-W]!==code[c]||
      code[c+W]!==code[c]?1:INF;
  }
  for(y=1;y<H;y++)for(x=1;x<W-1;x++){c=y*W+x;if(d[c]>1)
    d[c]=Math.min(d[c],d[c-1]+1,d[c-W]+1,d[c-W-1]+R2,d[c-W+1]+R2);}
  for(y=H-2;y>=0;y--)for(x=W-2;x>0;x--){c=y*W+x;if(d[c]>1)
    d[c]=Math.min(d[c],d[c+1]+1,d[c+W]+1,d[c+W+1]+R2,d[c+W-1]+R2);}
  var seen=new Uint8Array(WH),stack=new Int32Array(WH),comps=slots.map(function(){return [];});
  for(c=0;c<WH;c++){
    if(seen[c]||code[c]>K)continue;
    var cd=code[c],top=0,size=0,rec=0,best=c;stack[top++]=c;seen[c]=1;
    while(top){var q=stack[--top];size++;rec+=raw[q];if(d[q]>d[best])best=q;
      var qx=q%W,nb=[qx>0?q-1:-1,qx<W-1?q+1:-1,q>=W?q-W:-1,q+W<WH?q+W:-1];
      for(var m=0;m<4;m++){var r=nb[m];if(r>=0&&!seen[r]&&code[r]===cd){seen[r]=1;stack[top++]=r;}}}
    comps[cd].push({size:size,rec:rec,at:best});
  }
  function pt(c){var x=c%W,y=(c-x)/W;return [g.ext[0]+(x+.5)/g.sx,g.ext[1]+(y+.5)/g.sy];}
  var out=[];
  comps.forEach(function(cs,s){
    var row=slots[s].row;if(row<0||!cs.length)return;
    cs.sort(function(a,b){return b.size-a.size;});
    var area=cs.reduce(function(t,q){return t+q.size;},0),rec=cs.reduce(function(t,q){return t+q.rec;},0),
      size=.2*Math.sqrt(area)*g.cs,main={text:T[row][0],pos:pt(cs[0].at),size:size,row:row,area:area,italic:false};
    if(cs[0].size<8*sc*sc)return;
    out.push(main);
    var q=cs.slice(1).find(function(q){return q.rec>=rec/3;});
    if(q)out.push({text:T[row][0],pos:pt(q.at),size:size*.55,row:row,area:q.size,italic:true,of:main});
  });
  if(kOf){
    var kc=new Map();
    for(c=0;c<WH;c++){if(code[c]>K||kOf[code[c]]<0)continue;
      var e=kc.get(kOf[code[c]])||{n:0,x:0,y:0};e.n++;e.x+=c%W;e.y+=Math.floor(c/W);kc.set(kOf[code[c]],e);}
    kc.forEach(function(e,row){
      if(e.n<.01*nLand)return;
      var ang=Math.atan2(e.y/e.n-H/2,e.x/e.n-W/2),R0=.53*Math.max(W,H),
        cx=Math.round(W/2+R0*Math.cos(ang)),cy=Math.round(H/2+R0*Math.sin(ang));
      out.push({text:String(T[row][0]).toUpperCase()+'\n'+Math.round(100*e.n/nLand)+'% of map',
        pos:[g.ext[0]+cx/g.sx,g.ext[1]+cy/g.sy],size:.07*Math.sqrt(e.n)*g.cs,row:row,area:e.n,bold:true});
    });
  }
  return out;
}
// The labels that read at zoom z (2^z px a layout unit, as the text layer draws common units): kingdoms first,
// then the largest; a label goes when it would draw under minPx or overlap one already placed, and a repeat
// (d.of, its region's main label) when it would draw within REPEAT_PX of that label.
var REPEAT_PX=60;
function place(L,z,minPx){
  var k=Math.pow(2,z),out=[],box=[];
  function px(d){return Math.min(d.size*k,d.bold?22:30);}
  L.slice().sort(function(a,b){return (b.bold?1:0)-(a.bold?1:0)||px(b)-px(a)||b.area-a.area;}).forEach(function(d){
    var p=px(d);if(p<minPx||d.of&&Math.hypot(d.pos[0]-d.of.pos[0],d.pos[1]-d.of.pos[1])*k<REPEAT_PX)return;
    var ln=String(d.text).split('\n'),w=p*(d.bold?.62:.55)*Math.max.apply(null,ln.map(function(t){return t.length;}))/k/2,
      h=p*1.2*ln.length/k/2,b=[d.pos[0]-w,d.pos[1]-h,d.pos[0]+w,d.pos[1]+h];
    if(box.some(function(q){return b[0]<q[2]&&q[0]<b[2]&&b[1]<q[3]&&q[1]<b[3];}))return;
    box.push(b);out.push(d);
  });
  return out;
}
// What lies under layout point (x,y): the cell's region slot (-1 for none), its records, and the levels of
// the records within the look-alike blur's reach (one cell holds too few to read).
function hit(M,x,y){
  var ix=Math.floor((x-M.ext[0])*M.sx),iy=Math.floor((y-M.ext[1])*M.sy),W=M.W,H=M.H;
  if(ix<0||iy<0||ix>=W||iy>=H)return null;
  var c=iy*W+ix,cd=M.code[c],lev=null,r=Math.ceil(2*SIG_LOOK*M.sc);
  if(M.levels){lev=[0,0,0,0,0,0];
    for(var yy=Math.max(0,iy-r);yy<=Math.min(H-1,iy+r);yy++)for(var xx=Math.max(0,ix-r);xx<=Math.min(W-1,ix+r);xx++)
      for(var v=0;v<6;v++)lev[v]+=M.levels[v*W*H+yy*W+xx];}
  return {slot:cd<=M.K?cd:-1,sea:cd===SEA,outside:cd===OUTSIDE,n:M.raw[c],levels:lev};
}
return {RANKS:RANKS,FINE:FINE,LEVELS:LEVELS,RAMP:RAMP,ancestors:ancestors,rankOf:rankOf,canZoom:canZoom,
  decodeLookalike:decodeLookalike,level:level,build:build,hit:hit,place:place,tidy:tidy,extent:extent,region:region,
  focus:focus,shade:shade,hsl:hsl,SEA:SEA,OUTSIDE:OUTSIDE};
});
