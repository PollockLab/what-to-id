// The subtitle names the build date; say how old that is, and warn once it is stale.
var MapStale=(function(){
'use strict';
var STALE_DAYS=2;
function MapStale(DAY){
  var el=document.getElementById('updated'),t=el?Date.parse(el.getAttribute('datetime')+'T00:00:00Z'):NaN;
  if(isNaN(t))return;
  var n=new Date(),days=Math.floor((Date.UTC(n.getUTCFullYear(),n.getUTCMonth(),n.getUTCDate())-t)/DAY),
    before=el.previousSibling,after=el.nextSibling;
  if(!before||!after||before.nodeType!==3||after.nodeType!==3)return;
  if(days>STALE_DAYS){before.nodeValue='Last updated ';
    el.textContent=days+' days ago';after.nodeValue=after.nodeValue.replace(/^\./,'; some records may have an ID by now.');}
  else{before.nodeValue=before.nodeValue.replace(/ on $/,', updated ');
    el.textContent=days<=0?'today':days===1?'yesterday':days+' days ago';}
}
return MapStale;
})();
