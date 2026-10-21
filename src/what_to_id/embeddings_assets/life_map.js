// The map of life: the photo-space layout drawn as a political map. A grid over the layout gives each cell
// the clade whose smoothed record density is highest there. Zooming into a clade crops the view to the cells
// it holds and colours them by the rank below; no record is filtered out, so other clades' territory stays
// in view as grey. Agreement and look-alike levels come from pool-lookalike.bin (per record, measured on the
// full BioCLIP neighbours), never from distances on this plot. Pure: arrays in, pixels and labels out.
(function(root,factory){
  var api=factory();
  if(typeof module!=='undefined'&&module.exports)module.exports=api;else root.LifeMap=api;
})(typeof globalThis!=='undefined'?globalThis:this,function(){
'use strict';
var RANKS=['kingdom','phylum','class','order','family'];
// The rank each view's regions are drawn at: the rank below the clade's, as far as the file measures agreement.
var FINE={life:'class',kingdom:'class',phylum:'class','class':'order',order:'family'};
// Where Up goes from a clade of each rank.
var UP={phylum:'kingdom','class':'kingdom',order:'class'};
var LONG=512,SIG=0.8,SIG_LOOK=1.5,K_LIFE=28,K_ZOOM=12;
var CAT=[[42,120,214],[235,104,52],[27,175,122],[237,161,0],[232,123,164],[0,131,0],[98,80,214],[227,73,72]];
var OTHER=[179,179,168],OUT=219,NODATA=[225,224,217];
var RAMP=[[205,226,251],[158,197,244],[109,167,236],[57,135,229],[37,106,191],[24,79,149],[13,54,107]];
var LEVELS=['same family','same order','same class','same phylum','same kingdom','other kingdom'];
var SEA=255,OUTSIDE=254;  // cell codes past the region slots

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
// The clade Up goes to from row, or -1 for the whole of life.
function parentOf(A,T,ranks,row){var u=UP[rankOf(T,ranks,row)];return u?A[u][row]:-1;}

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
function grid(ext){
  var dx=ext[2]-ext[0]||1,dy=ext[3]-ext[1]||1,cs=Math.max(dx,dy)/LONG,
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
// The zoom's crop: the life-level cells where the clade holds over half the smoothed density, boxed by the
// quantiles of its records there. A clade with no such cells gets the box of all its records.
function territoryExtent(o,inTax){
  var g=grid(lifeExtent(o.pos,o.n)),WH=g.W*g.H,cell=cellsOf(o.pos,o.n,g),tot=new Float32Array(WH),
    cz=new Float32Array(WH),raw,tmp=new Float32Array(WH),k=kernel(SIG),i;
  for(i=0;i<o.n;i++){var c=cell[i];if(c<0)continue;tot[c]++;if(inTax[o.tax[i]])cz[c]++;}
  raw=cz.slice();blur(tot,g.W,g.H,k,tmp);blur(cz,g.W,g.H,k,tmp);
  var land=landOf(tot),hx=new Float64Array(g.W),hy=new Float64Array(g.H),m=0;
  for(var pass=0;pass<2&&!m;pass++)for(i=0;i<WH;i++){
    if(!raw[i]||(!pass&&!(land[i]&&cz[i]>.5*tot[i])))continue;
    hx[i%g.W]+=raw[i];hy[Math.floor(i/g.W)]+=raw[i];m+=raw[i];}
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

// o: {pos (x,y per point), n, tax (taxa row per point, 65535 unknown), grp (group per point), groups (count),
// color(g) -> rgb, T, ranks, A (ancestors), clade (taxa row, -1 for the whole of life), look (decodeLookalike,
// or null), src (each point's row in the look-alike file)}.
function build(o){
  var T=o.T,R=T.length,A=o.A,clade=o.clade==null?-1:o.clade,zr=rankOf(T,o.ranks,clade),fine=FINE[zr];
  if(!fine)throw new Error('cannot zoom into a '+zr);
  var NT=65536,inTax=new Uint8Array(NT),fineOf=new Int32Array(NT).fill(-1),t,i;
  for(t=0;t<NT;t++){inTax[t]=clade<0||(t<R&&A[zr][t]===clade)?1:0;if(t<R)fineOf[t]=A[fine][t];}
  var ext=clade<0?lifeExtent(o.pos,o.n):territoryExtent(o,inTax);
  if(!ext)return null;
  var g=grid(ext),W=g.W,H=g.H,WH=W*H,cell=cellsOf(o.pos,o.n,g);
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
  var raw=tot.slice(),tmp=new Float32Array(WH),k=kernel(SIG),kl=kernel(SIG_LOOK);
  for(s=0;s<=K;s++)blur(S.subarray(s*WH,(s+1)*WH),W,H,k,tmp);
  blur(tot,W,H,k,tmp);
  if(L){blur(aS,W,H,k,tmp);blur(aC,W,H,k,tmp);blur(vS,W,H,kl,tmp);blur(vC,W,H,kl,tmp);}
  var land=landOf(tot),code=new Uint8Array(WH),dom=new Float32Array(WH),nLand=0;
  for(c=0;c<WH;c++){
    if(!land[c]){code[c]=SEA;continue;}
    nLand++;var best=0,mx=-1,sum=0;
    for(s=0;s<=K;s++){var d=S[s*WH+c];sum+=d;if(d>mx){mx=d;best=s;}}
    if(clade>=0&&!(sum>.5*tot[c])){code[c]=OUTSIDE;continue;}
    code[c]=best;dom[c]=mx/((clade<0?tot[c]:sum)||1);
  }
  // colours: at life a class takes its group's colour, siblings in one group paler; inside a zoom, a palette
  var seen={},slots=rows.map(function(row,s){
    var rgb;
    if(clade<0){var bg=0;for(var q=1;q<G;q++)if(sGrp[s*G+q]>sGrp[s*G+bg])bg=q;
      var sib=seen[bg]=(seen[bg]===undefined?-1:seen[bg])+1;rgb=mix(o.color(bg),WHITE,.28*(sib%3));}
    else rgb=s<8?CAT[s]:mix(CAT[s-8],WHITE,.38);
    return {row:row,rgb:rgb,n:sN[s],agree:sAc[s]?sA[s]/sAc[s]:null};
  });
  slots.push({row:-1,rgb:OTHER,n:sN[K],agree:null});
  var kOf=slots.map(function(sl){return sl.row>=0?A.kingdom[sl.row]:-1;}),
    img=new Uint8ClampedArray(4*WH),look=L?new Uint8ClampedArray(4*WH):null;
  function put(a,c,rgb,al){var p=4*((H-1-Math.floor(c/W))*W+c%W);a[p]=rgb[0];a[p+1]=rgb[1];a[p+2]=rgb[2];a[p+3]=al;}
  for(c=0;c<WH;c++){
    var cd=code[c];
    if(cd===SEA)continue;
    if(cd===OUTSIDE){put(img,c,[OUT,OUT,OUT],255);if(look)put(look,c,[OUT,OUT,OUT],255);continue;}
    // contested cells, and cells whose records' photo neighbours mostly lie outside their clade, read paler
    var f=.35+.65*dom[c]*(aC[c]>.05?Math.min(1,aS[c]/aC[c]):1);
    put(img,c,mix(slots[cd].rgb,WHITE,1-f),255);
    if(look)put(look,c,vC[c]>.05?ramp(vS[c]/vC[c]/3):NODATA,255);
  }
  borders(img,code,W,H,clade<0?kOf:null);
  return {ext:ext,W:W,H:H,cs:g.cs,sx:g.sx,sy:g.sy,clade:clade,rank:zr,fine:fine,code:code,raw:raw,levels:LH,
    slots:slots,K:K,image:img,look:look,labels:labels(code,W,H,g,slots,T,K,clade<0?kOf:null,nLand)};
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
// A label at the pole of inaccessibility of each region's largest island, italic repeats on the next two
// sizeable ones, and at life each kingdom's share of the map around the edge. Sizes are in layout units.
function labels(code,W,H,g,slots,T,K,kOf,nLand){
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
    var cd=code[c],top=0,size=0,best=c;stack[top++]=c;seen[c]=1;
    while(top){var q=stack[--top];size++;if(d[q]>d[best])best=q;
      var qx=q%W,nb=[qx>0?q-1:-1,qx<W-1?q+1:-1,q>=W?q-W:-1,q+W<WH?q+W:-1];
      for(var m=0;m<4;m++){var r=nb[m];if(r>=0&&!seen[r]&&code[r]===cd){seen[r]=1;stack[top++]=r;}}}
    comps[cd].push({size:size,at:best});
  }
  function pt(c){var x=c%W,y=(c-x)/W;return [g.ext[0]+(x+.5)/g.sx,g.ext[1]+(y+.5)/g.sy];}
  var out=[];
  comps.forEach(function(cs,s){
    var row=slots[s].row;if(row<0||!cs.length)return;
    cs.sort(function(a,b){return b.size-a.size;});
    var area=cs.reduce(function(t,q){return t+q.size;},0),size=.2*Math.sqrt(area)*g.cs;
    if(cs[0].size<8)return;
    out.push({text:T[row][0],pos:pt(cs[0].at),size:size,row:row,area:area,italic:false});
    cs.slice(1,3).forEach(function(q){
      if(q.size>.08*area&&q.size>40)out.push({text:T[row][0],pos:pt(q.at),size:size*.55,row:row,area:q.size,italic:true});});
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
// What lies under layout point (x,y): the cell's region slot (-1 for none), its records, and the levels of
// the records within the look-alike blur's reach (one cell holds too few to read).
function hit(M,x,y){
  var ix=Math.floor((x-M.ext[0])*M.sx),iy=Math.floor((y-M.ext[1])*M.sy),W=M.W,H=M.H;
  if(ix<0||iy<0||ix>=W||iy>=H)return null;
  var c=iy*W+ix,cd=M.code[c],lev=null,r=Math.ceil(2*SIG_LOOK);
  if(M.levels){lev=[0,0,0,0,0,0];
    for(var yy=Math.max(0,iy-r);yy<=Math.min(H-1,iy+r);yy++)for(var xx=Math.max(0,ix-r);xx<=Math.min(W-1,ix+r);xx++)
      for(var v=0;v<6;v++)lev[v]+=M.levels[v*W*H+yy*W+xx];}
  return {slot:cd<=M.K?cd:-1,sea:cd===SEA,outside:cd===OUTSIDE,n:M.raw[c],levels:lev};
}
return {RANKS:RANKS,FINE:FINE,LEVELS:LEVELS,RAMP:RAMP,ancestors:ancestors,rankOf:rankOf,canZoom:canZoom,
  parentOf:parentOf,decodeLookalike:decodeLookalike,level:level,build:build,hit:hit};
});
