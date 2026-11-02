// Test helpers for test_clade_colour_js.py, run in node after map_filter.js and clade_colour.js.
// Page contrast as tree_model.js has it.
var BG=[[251,251,249],[26,26,25]];
var lum=(c)=>c.reduce((s,v,i)=>{v/=255;v=v<=0.04045?v/12.92:Math.pow((v+0.055)/1.055,2.4);return s+v*[0.2126,0.7152,0.0722][i];},0);
var contrast=(a,b)=>{const x=lum(a)+0.05,y=lum(b)+0.05;return Math.max(x,y)/Math.min(x,y);};
var de=CladeColour.de,sim=CladeColour.sim,CVD=CladeColour.CVD;  // CIEDE2000 and the Machado 2009 simulations
var least=(cs)=>{let m=Infinity;cs.forEach((a,i)=>cs.slice(i+1).forEach((b)=>{m=Math.min(m,de(a,b));}));return m;};
// The tree's colours before clade_colour.js: the group colour mixed toward white or black by its sub-clade's
// place under the group, backed off until it read on both pages.
var TONES=[0,0.45,-0.35,0.25,-0.2,0.6,-0.5,0.12,-0.1];
function old(rgb,t){for(let k=0;k<8&&t;k++,t/=2){const to=t>0?255:0,c=rgb.map((v)=>Math.round(v+(to-v)*Math.abs(t)));
  if(BG.every((b)=>contrast(c,b)>=2))return c;}return rgb.slice();}
