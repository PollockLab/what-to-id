// The modelled range of the one picked taxon: the ECCC 1 km habitat model (META.sdm, sdm_manifest.py) as tiles from
// the Biodiversite Quebec tiler, under the taxon's iNaturalist range outline, with a legend under the toggle. Offered only for exactly one
// included pick with a model; the sources are removed when off, so no tiles load then. A basemap-coloured mask
// (META.files.sdmmask, fetched when first on) covers the model and its outline outside Canada and the USA.
// MapSdm(map,ctx), ctx {META, get(url) a data file's bytes, picks() the taxon picks, TAXA(), cells(name) the range as IdentifyRanges.cells gives it}.
// sync() after the picks change and after the range file arrives.
var MapSdm=(function(){
'use strict';
var dark=matchMedia('(prefers-color-scheme: dark)').matches,
  TILES='https://tiler2.biodiversite-quebec.ca/cog/tiles/WebMercatorQuad/{z}/{x}/{y}.png?url=',
  STYLE='&colormap_name=viridis&rescale=0,99&nodata=255',
  LAND=dark?'#0e0e0e':'#fafaf8',SEA=dark?'#2c353c':'#d4dadc',  // the Carto basemap's background and water
  VIRIDIS='linear-gradient(to right,#440154,#3b528b,#21918c,#5ec962,#fde725)';
function el(tag,cls,text){var e=document.createElement(tag);if(cls)e.className=cls;if(text!=null)e.textContent=text;return e;}
// The range's outline: the cell edges no other range cell shares (the grid's vertices are rounded, so shared ones match).
function edges(g){
  var c={},e=[];
  g.coordinates.forEach(function(p){var r=p[0];for(var k=0;k+1<r.length;k++){
    var a=String(r[k]),b=String(r[k+1]),key=a<b?a+'|'+b:b+'|'+a;
    c[key]=(c[key]||0)+1;if(c[key]===1)e.push([key,r[k],r[k+1]]);}});
  return {type:'MultiLineString',coordinates:e.filter(function(x){return c[x[0]]===1;}).map(function(x){return [x[1],x[2]];})};
}
return function(map,ctx){
  var btn=document.getElementById('sdmbtn'),ON=false,KEY=null,  // KEY: the model drawn
    leg=el('div','sdmleg'),bar=el('span','sdmbar'),line=el('span','sdmline');
  bar.style.background=VIRIDIS;leg.hidden=true;
  [[bar,'Habitat model (ECCC 1 km, 1980-2010 climate): low to high'],[line,'iNaturalist range map']].forEach(function(x){
    var r=el('p');r.append(x[0],el('span',null,x[1]));leg.appendChild(r);});
  if(btn)btn.after(leg);  // in the panel under the toggle: over the map it would cover the area controls
  // the one included pick's name and model, or null
  function one(){
    var p=ctx.picks(),T=ctx.TAXA(),m=ctx.META.sdm;
    if(!btn||!m||!T||p.length!==1||p[0].not)return null;
    var r=T.findIndex(function(t){return t[2]===p[0].id;}),s=r>=0&&m.taxa[r];
    return s?{name:T[r][0],cog:m.cog.replace('{slug}',s)}:null;
  }
  function off(){
    ['sdm-range','sdm-mask','sdm'].forEach(function(id){if(map.getLayer(id))map.removeLayer(id);if(map.getSource(id))map.removeSource(id);});
    KEY=null;leg.hidden=true;
  }
  function draw(t){
    if(!map.isStyleLoaded()){map.once('idle',sync);return;}
    var under=map.getLayer('area-line')?'area-line':undefined,g;  // the drawn area stays on top
    if(!map.getSource('sdm')){
      map.addSource('sdm',{type:'raster',tiles:[TILES+encodeURIComponent(t.cog)+STYLE],tileSize:256,
        attribution:'ECCC SDM via Biodiversité Québec'});
      map.addLayer({id:'sdm',type:'raster',source:'sdm',paint:{'raster-opacity':.55}},under);
    }
    if(!map.getSource('sdm-range')&&(g=ctx.cells(t.name))){
      map.addSource('sdm-range',{type:'geojson',data:{type:'Feature',properties:{},geometry:edges(g)}});
      map.addLayer({id:'sdm-range',type:'line',source:'sdm-range',paint:{'line-width':2,
        'line-color':getComputedStyle(document.documentElement).getPropertyValue('--rlab').trim()||'#3b78c4'}},under);
    }
    KEY=t.cog;leg.hidden=false;
    if(!map.getSource('sdm-mask'))ctx.get(ctx.META.files.sdmmask).then(function(b){  // the model is 0, not nodata, outside CA and US
      if(KEY!==t.cog||map.getSource('sdm-mask'))return;  // went off, or another call won
      map.addSource('sdm-mask',{type:'geojson',data:JSON.parse(new TextDecoder().decode(b))});
      map.addLayer({id:'sdm-mask',type:'fill',source:'sdm-mask',
        paint:{'fill-color':['match',['get','id'],'sea',SEA,LAND]}},map.getLayer('sdm-range')?'sdm-range':under);
    }).catch(function(){});
  }
  function sync(){
    var t=one();
    if(btn)btn.hidden=!t;
    if(!t||KEY&&KEY!==t.cog)ON=false;  // a new pick starts with the overlay off
    if(btn)btn.setAttribute('aria-pressed',String(ON));
    if(ON)draw(t);else off();
  }
  if(btn)btn.onclick=function(){ON=!ON;sync();};
  return {sync:sync};
};
})();
