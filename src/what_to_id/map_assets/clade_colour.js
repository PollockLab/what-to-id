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
// The palette for taxa table T: col[row] is [r,g,b] for each row at or below a group taxon, else undefined; kids
// the children in palette order, par the parents with each group taxon cut loose (as the tree has them), gr the
// row of each group's taxon by group name.
function build(T,META){
  var n=T.length,par=new Int32Array(n),tot=new Float64Array(n),kids=[],col=new Array(n),gr={},G={},i,j,has=n&&T[0].length>5;
  Object.keys(META.group_ids||{}).forEach(function(g){G[META.group_ids[g]]=g;});
  if(META.groups.indexOf('Animalia')>=0)G[1]=G[1]||'Animalia';  // iNaturalist's iconic Animalia, as the tree reads it
  for(i=0;i<n;i++){kids.push([]);par[i]=G[T[i][2]]||!(T[i].length>4)?-1:T[i][4];}
  for(i=0;i<n;i++)if(T[i][5])for(j=i;j>=0;j=par[j])tot[j]+=T[i][5];
  for(i=0;i<n;i++)if(par[i]>=0&&(tot[i]||!has))kids[par[i]].push(i);
  kids.forEach(function(k){k.sort(function(a,b){return tot[b]-tot[a]||a-b;});});
  function paint(r,lo,hi,L,C,d){var k=kids[r],m=k.length,w=(hi-lo)/m;
    var o=order(m);k.forEach(function(c,i){var p=o[i],h=lo+(p+0.5)*w,
      l=d?Math.min(HI,Math.max(LO,(L+L1)/2+0.02+DL[p%3]*0.8)):L1+DL[p%3];
      col[c]=make(l,C,h);paint(c,h-F*w/2,h+F*w/2,l,C*0.88,d+1);});}
  for(i=0;i<n;i++)if(G[T[i][2]]){var g=G[T[i][2]],c0=MapFilter.color(g,META.groups.indexOf(g)),o=lab(c0),
    C=Math.hypot(o[1],o[2]),h=Math.atan2(o[2],o[1])*180/Math.PI,w=Math.min(CAP,PER*kids[i].length);
    gr[g]=i;col[i]=c0.slice();
    // a grey group (Animalia) has no hue to keep: its clades take soft hues round the whole circle
    if(C<0.03)paint(i,0,360,L1,0.08,0);else paint(i,h-w/2,h+w/2,L1,Math.max(C,0.13),0);}
  return {col:col,kids:kids,par:par,gr:gr,tot:tot};
}
return {build:build,lab:lab,make:make,reads:reads};
})();
