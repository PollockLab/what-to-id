// Clade colours shared by the tree of life and the map: each life group keeps its map colour (MapFilter.color) at
// its taxon, and the clades below it take colours from it as in Tennekes and de Jonge's Tree Colors (IEEE TVCG
// 2014), in OKLCH: a node's children split its hue range, each child keeping F of its share for its own children,
// in an interleaved order so neighbours in the list sit far apart in hue, with lightness alternating along the
// hue as a second channel. Deeper rows lose a little chroma. Every colour keeps 2:1 against both page backgrounds.
// The colours read only the taxa table (pool-taxa.bin: [latin, common, iNaturalist id, rank, parent row, own
// records]) and META, which both pages share, so a clade has one colour on both. Siblings sort by the table's
// own records summed below them, most first (as the tree's build does), ties by row.
var CladeColour=(function(){
'use strict';
var F=0.75,PER=28,CAP=150,L1=0.62,DL=[0,0.1,-0.1],LO=0.47,HI=0.76,
  BG=[[251,251,249],[26,26,25]].map(function(c){return lum(lin(c));});
function lin(c){return c.map(function(v){v/=255;return v<=0.04045?v/12.92:Math.pow((v+0.055)/1.055,2.4);});}
function lum(l){return 0.2126*l[0]+0.7152*l[1]+0.0722*l[2];}
// sRGB 0-255 to OKLab and OKLab to linear sRGB (Ottosson's matrices)
function lab(c){var x=lin(c),l=Math.cbrt(0.4122214708*x[0]+0.5363325363*x[1]+0.0514459929*x[2]),
  m=Math.cbrt(0.2119034982*x[0]+0.6806995451*x[1]+0.1073969566*x[2]),s=Math.cbrt(0.0883024619*x[0]+0.2817188376*x[1]+0.6299787005*x[2]);
  return [0.2104542553*l+0.7936177850*m-0.0040720468*s,1.9779984951*l-2.4285922050*m+0.4505937099*s,
    0.0259040371*l+0.7827717662*m-0.8086757660*s];}
function linOf(L,C,h){var a=C*Math.cos(h*Math.PI/180),b=C*Math.sin(h*Math.PI/180),
  l=Math.pow(L+0.3963377774*a+0.2158037573*b,3),m=Math.pow(L-0.1055613458*a-0.0638541728*b,3),s=Math.pow(L-0.0894841775*a-1.2914855480*b,3);
  return [4.0767416621*l-3.3077115913*m+0.2309699292*s,-1.2684380046*l+2.6097574011*m-0.3413193965*s,
    -0.0041960863*l-0.7034186147*m+1.7076147010*s];}
function inG(x){return x.every(function(v){return v>=-1e-4&&v<=1+1e-4;});}
function rgb(x){return x.map(function(v){v=Math.min(1,Math.max(0,v));
  return Math.round(255*(v<=0.0031308?12.92*v:1.055*Math.pow(v,1/2.4)-0.055));});}
// CIEDE2000 (Sharma, Wu and Dalal 2005) between sRGB colours, via CIELAB under D65
function cielab(c){var x=lin(c),f=function(t){return t>216/24389?Math.cbrt(t):(24389/27*t+16)/116;},
  X=f((0.4124564*x[0]+0.3575761*x[1]+0.1804375*x[2])/0.95047),Y=f(0.2126729*x[0]+0.7151522*x[1]+0.0721750*x[2]),
  Z=f((0.0193339*x[0]+0.1191920*x[1]+0.9503041*x[2])/1.08883);
  return [116*Y-16,500*(X-Y),200*(Y-Z)];}
function de(p,q){var u=cielab(p),v=cielab(q),r=Math.PI/180,P7=function(c){c=Math.pow(c,7);return Math.sqrt(c/(c+6103515625));},
  G=0.5*(1-P7((Math.hypot(u[1],u[2])+Math.hypot(v[1],v[2]))/2)),A1=u[1]*(1+G),A2=v[1]*(1+G),
  C1=Math.hypot(A1,u[2]),C2=Math.hypot(A2,v[2]),h1=(Math.atan2(u[2],A1)/r+360)%360,h2=(Math.atan2(v[2],A2)/r+360)%360,
  dh=C1*C2?h2-h1:0,Lb=(u[0]+v[0])/2-50,Cp=(C1+C2)/2,hb=h1+h2;
  dh-=dh>180?360:dh<-180?-360:0;if(C1*C2)hb=Math.abs(h1-h2)>180?(hb+(hb<360?360:-360))/2:hb/2;
  var T=1-0.17*Math.cos((hb-30)*r)+0.24*Math.cos(2*hb*r)+0.32*Math.cos((3*hb+6)*r)-0.2*Math.cos((4*hb-63)*r),
    dL=(v[0]-u[0])/(1+0.015*Lb*Lb/Math.sqrt(20+Lb*Lb)),dC=(C2-C1)/(1+0.045*Cp),dH=2*Math.sqrt(C1*C2)*Math.sin(dh*r/2)/(1+0.015*Cp*T),
    RT=-2*P7(Cp)*Math.sin(60*Math.exp(-Math.pow((hb-275)/25,2))*r);
  return Math.sqrt(dL*dL+dC*dC+dH*dH+RT*dC*dH);}
// Colour-vision deficiency as Machado, Oliveira and Fernandes (IEEE TVCG 2009) simulate it, severity 1.0, in linear RGB
var CVD={protanopia:[[0.152286,1.052583,-0.204868],[0.114503,0.786281,0.099216],[-0.003882,-0.048116,1.051998]],
  deuteranopia:[[0.367322,0.860646,-0.227968],[0.280085,0.672501,0.047413],[-0.011820,0.042940,0.968881]],
  tritanopia:[[1.255528,-0.076749,-0.178779],[-0.078411,0.930809,0.147602],[0.004733,0.691367,0.303900]]};
function sim(c,k){var x=lin(c);return CVD[k].map(function(r){var v=Math.min(1,Math.max(0,r[0]*x[0]+r[1]*x[1]+r[2]*x[2]));
  return 255*(v<=0.0031308?12.92*v:1.055*Math.pow(v,1/2.4)-0.055);});}
// [least CIEDE2000 between colours cs over normal vision and the three simulations, least under normal vision]
function sep(cs){var v=[cs].concat(Object.keys(CVD).map(function(k){return cs.map(function(c){return sim(c,k);});}))
  .map(function(x){var m=Infinity;x.forEach(function(a,i){for(var j=i+1;j<x.length;j++)m=Math.min(m,de(a,x[j]));});return m;});
  return [Math.min.apply(null,v),v[0]];}
function reads(c){var y=lum(lin(c))+0.05;return BG.every(function(b){return Math.max(y,b+0.05)/Math.min(y,b+0.05)>=2;});}
// OKLCH to sRGB: chroma cut to the gamut, then lightness moved toward the middle until it reads on both pages.
function make(L,C,h){var c;
  for(var k=0;k<40;k++,L+=L<L1?0.01:-0.01){var lo=0,hi=C;
    if(!inG(linOf(L,hi,h)))for(var j=0;j<16;j++){var m=(lo+hi)/2;if(inG(linOf(L,m,h)))lo=m;else hi=m;}
    else lo=hi;
    c=rgb(linOf(L,lo,h));if(reads(c))return c;}
  return c;}
// The hue share each list position of m takes, in bit-reversed order from the middle (m/2, 0, 3m/4, m/4, ...):
// the biggest child keeps its parent's hue, neighbours in the list sit far apart, and so do the first few (those
// the map's legend shows) of a long list.
var ORD={};
function order(m){if(ORD[m])return ORD[m];var b=1,o=[],i,r,k;while(b<m)b*=2;
  for(i=0;i<b;i++){for(r=0,k=1;k<b;k*=2)r=r*2+(i&k?1:0);if(r<m)o.push((r+(m>>1))%m);}
  return ORD[m]=o;}
// The palette for taxa table T: col[row] is [r,g,b] for each row at or below a group taxon, else undefined; at(f)
// the same focused on row f; kids the children in palette order, par the parents with each group taxon cut loose
// (as the tree has them), gr the row of each group's taxon by group name.
function build(T,META){
  var n=T.length,par=new Int32Array(n),tot=new Float64Array(n),kids=[],col=new Array(n),gr={},G={},i,j,has=n&&T[0].length>5;
  Object.keys(META.group_ids||{}).forEach(function(g){G[META.group_ids[g]]=g;});
  if(META.groups.indexOf('Animalia')>=0)G[1]=G[1]||'Animalia';  // iNaturalist's iconic Animalia, as the tree reads it
  for(i=0;i<n;i++){kids.push([]);par[i]=G[T[i][2]]||!(T[i].length>4)?-1:T[i][4];}
  for(i=0;i<n;i++)if(T[i][5])for(j=i;j>=0;j=par[j])tot[j]+=T[i][5];
  for(i=0;i<n;i++)if(par[i]>=0&&(tot[i]||!has))kids[par[i]].push(i);
  kids.forEach(function(k){k.sort(function(a,b){return tot[b]-tot[a]||a-b;});});
  // s turns the slots, q flips the lightness steps; top colours only the first 8 children, not below
  function paint(r,lo,hi,L,C,d,s,q,top){var k=kids[r],m=k.length,w=(hi-lo)/m;
    var o=order(m);(top?k.slice(0,8):k).forEach(function(c,i){var p=(o[i]+(s|0))%m,h=lo+(p+0.5)*w,t=q?-DL[p%3]:DL[p%3],
      l=d?Math.min(HI,Math.max(LO,(L+L1)/2+0.02+t*0.8)):L1+t;
      col[c]=make(l,C,h);if(!top)paint(c,h-F*w/2,h+F*w/2,l,C*0.88,d+1);});}
  // a wedge root: a group's taxon in colour c0, or (all) a focus in its own colour over the whole hue circle
  function root(i,c0,all){var o=lab(c0),C=Math.hypot(o[1],o[2]),h=Math.atan2(o[2],o[1])*180/Math.PI,
    m=kids[i].length,w=all?360:Math.min(CAP,PER*m),lo=all?h-((m>>1)+0.5)*w/m:h-w/2;col[i]=c0.slice();
    // a grey group (Animalia) has no hue to keep: its clades take soft hues round the whole circle
    if(C<0.03)return paint(i,0,360,L1,0.08,0);C=Math.max(C,0.13);
    // a focus takes, of its slots turned 0 to 7 steps and its lightness flipped or not, the arrangement whose first 8
    // children stay furthest apart under normal vision and all three simulations, ties by normal vision
    for(var s=0,b=[0,0],z=[-1,-1];all&&s<Math.min(8,m);s++)for(var q=0;q<2;q++){paint(i,lo,lo+w,L1,C,0,s,q,1);
      var e=sep(kids[i].slice(0,8).map(function(r){return col[r];}));if(e[0]>z[0]||e[0]===z[0]&&e[1]>z[1])z=e,b=[s,q];}
    paint(i,lo,lo+w,L1,C,0,b[0],b[1]);}
  for(i=0;i<n;i++)if(G[T[i][2]]){var g=G[T[i][2]];gr[g]=i;root(i,MapFilter.color(g,META.groups.indexOf(g)));}
  // The palette focused on row f below a group: f keeps its colour and its clades span the whole hue circle, since
  // the trail names the group: a wedge alone cannot part eight siblings for a colour-blind reader. The overview
  // (col) for any other f.
  var fc=[-1,col];
  function at(f){if(f===fc[0])return fc[1];var all=col;
    if(f>=0&&f<n&&all[f]&&par[f]>=0){col=all.slice();root(f,all[f],1);}
    fc=[f,col];col=all;return fc[1];}
  return {col:col,kids:kids,par:par,gr:gr,tot:tot,at:at};
}
return {build:build,lab:lab,make:make,reads:reads,de:de,sim:sim,CVD:CVD};
})();
