// Test helpers for test_clade_colour_js.py, run in node after map_filter.js and clade_colour.js.
// Page contrast as tree_model.js has it.
var BG=[[251,251,249],[26,26,25]];
var lum=(c)=>c.reduce((s,v,i)=>{v/=255;v=v<=0.04045?v/12.92:Math.pow((v+0.055)/1.055,2.4);return s+v*[0.2126,0.7152,0.0722][i];},0);
var contrast=(a,b)=>{const x=lum(a)+0.05,y=lum(b)+0.05;return Math.max(x,y)/Math.min(x,y);};
// CIEDE2000 (Sharma, Wu and Dalal 2005) between sRGB colours, via CIELAB under D65.
function cielab(c){const x=c.map(v=>{v/=255;return v<=0.04045?v/12.92:Math.pow((v+0.055)/1.055,2.4);});
  const X=(0.4124564*x[0]+0.3575761*x[1]+0.1804375*x[2])/0.95047,Y=0.2126729*x[0]+0.7151522*x[1]+0.0721750*x[2],
    Z=(0.0193339*x[0]+0.1191920*x[1]+0.9503041*x[2])/1.08883,f=t=>t>216/24389?Math.cbrt(t):(24389/27*t+16)/116;
  return [116*f(Y)-16,500*(f(X)-f(Y)),200*(f(Y)-f(Z))];}
function de(p,q){const [L1,a1,b1]=cielab(p),[L2,a2,b2]=cielab(q),r=Math.PI/180,
  Cb=(Math.hypot(a1,b1)+Math.hypot(a2,b2))/2,G=0.5*(1-Math.sqrt(Cb**7/(Cb**7+25**7))),
  A1=a1*(1+G),A2=a2*(1+G),C1=Math.hypot(A1,b1),C2=Math.hypot(A2,b2),
  h1=(Math.atan2(b1,A1)/r+360)%360,h2=(Math.atan2(b2,A2)/r+360)%360,dL=L2-L1,dC=C2-C1;
  let dh=C1*C2?h2-h1:0;if(dh>180)dh-=360;else if(dh<-180)dh+=360;
  const dH=2*Math.sqrt(C1*C2)*Math.sin(dh*r/2),Lb=(L1+L2)/2,Cp=(C1+C2)/2;
  let hb=h1+h2;if(C1*C2)hb=Math.abs(h1-h2)>180?(h1+h2+(h1+h2<360?360:-360))/2:(h1+h2)/2;
  const T=1-0.17*Math.cos((hb-30)*r)+0.24*Math.cos(2*hb*r)+0.32*Math.cos((3*hb+6)*r)-0.2*Math.cos((4*hb-63)*r),
    SL=1+0.015*(Lb-50)**2/Math.sqrt(20+(Lb-50)**2),SC=1+0.045*Cp,SH=1+0.015*Cp*T,
    RT=-2*Math.sqrt(Cp**7/(Cp**7+25**7))*Math.sin(60*Math.exp(-(((hb-275)/25)**2))*r);
  return Math.sqrt((dL/SL)**2+(dC/SC)**2+(dH/SH)**2+RT*(dC/SC)*(dH/SH));}
var least=(cs)=>{let m=Infinity;cs.forEach((a,i)=>cs.slice(i+1).forEach((b)=>{m=Math.min(m,de(a,b));}));return m;};
// The tree's colours before clade_colour.js: the group colour mixed toward white or black by its sub-clade's
// place under the group, backed off until it read on both pages.
var TONES=[0,0.45,-0.35,0.25,-0.2,0.6,-0.5,0.12,-0.1];
function old(rgb,t){for(let k=0;k<8&&t;k++,t/=2){const to=t>0?255:0,c=rgb.map((v)=>Math.round(v+(to-v)*Math.abs(t)));
  if(BG.every((b)=>contrast(c,b)>=2))return c;}return rgb.slice();}
