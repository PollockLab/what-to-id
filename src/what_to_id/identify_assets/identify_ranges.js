// Range maps on the Identify cards (pool-levels-range.bin, format in pool_levels.py). Beside Identify a chip gives the
// verdict in a few words and opens one shared popover: BC grid cells, label-only / look-alike-only / both, the record.
// Over the level, the far-outside control (All / Hide / Only) in #rout; Clear matches start with records far outside left out.
// IdentifyRanges(buf,ctx), ctx {P, name(i) the label, look(i) the look-alike or null, redraw()}. The map's record card
// takes only the chip and its popover (chip(i,lv)); it has no #rout, so no segmented control.
var IdentifyRanges=(function(){
'use strict';
// OUT_KM: a res-4 cell is ~22 km across, so under 50 km is cell-edge noise, not a range outlier.
var OUT_KM=50,NONE=255,KX=Math.cos(54*Math.PI/180),NEITHER='Outside both ranges: maybe neither.',
  REFS=[['Vancouver',-123120,49280],['Prince George',-122750,53920]];
function $(id){return document.getElementById(id);}
function el(tag,cls,text){var e=document.createElement(tag);if(cls)e.className=cls;if(text!=null)e.textContent=text;return e;}
function svg(tag,attrs){var e=document.createElementNS('http://www.w3.org/2000/svg',tag);
  for(var k in attrs)e.setAttribute(k,attrs[k]);return e;}
function pin(){
  var s=svg('svg',{viewBox:'0 0 16 16',width:12,height:12,'aria-hidden':'true'});
  s.appendChild(svg('path',{d:'M8 15s5-4.5 5-8.2A5 5 0 0 0 3 6.8C3 10.5 8 15 8 15z',fill:'none',
    stroke:'currentColor','stroke-width':1.6,'stroke-linejoin':'round'}));
  s.appendChild(svg('circle',{cx:8,cy:6.8,r:1.8,fill:'currentColor'}));return s;
}
function inside(g,x,y){
  for(var k=0,n=g.length,r=false,j=n-2;k<n;j=k,k+=2)
    if((g[k+1]>y)!==(g[j+1]>y)&&x<(g[j]-g[k])*(y-g[k+1])/(g[j+1]-g[k+1])+g[k])r=!r;
  return r;
}
return function(buf,ctx){
  var P=ctx.P,n=P.n,dv=new DataView(buf),size=dv.getUint32(0,true);
  if(buf.byteLength!==4+size+2*n)throw new Error('the range file holds '+buf.byteLength+' bytes, expected '+(4+size+2*n));
  var D=JSON.parse(new TextDecoder().decode(new Uint8Array(buf,4,size))),OKM=new Uint8Array(buf,4+size,n),NOTE=new Uint8Array(buf,4+size+n,n),
    RI=new Map(D.names.map(function(x,k){return [x,k];})),memo=[],BOX=null,OUTL=null,
    S={lv:0,o:0},Q={i:-1,lv:0,chip:null,pin:false,t:0},pop=null;  // S.o: 0 all, 1 only far outside, -1 hide far outside
  // a name's bitset over the grid cells, null when its range is unknown
  function bits(name){
    var k=name==null?undefined:RI.get(name);
    if(k===undefined)return null;
    if(memo[k])return memo[k];
    var b=atob(D.rng[k]),a=new Uint8Array(b.length);
    for(var j=0;j<b.length;j++)a[j]=b.charCodeAt(j);
    return(memo[k]=a);
  }
  function has(a,c){return c>=0&&(a[c>>3]>>(c&7))&1;}
  // okm_code back to km, already rounded as the page shows it: a coarser step farther out
  function km(i){var c=OKM[i];return c<50?c:c<=95?50+(c-50)*10:c<=105?500+(c-95)*50:1000+(c-105)*100;}
  function kmText(i){return km(i).toLocaleString('en');}
  function far(i){return OKM[i]!==NONE&&OKM[i]>=OUT_KM;}
  function near(i){return !far(i);}  // an unknown range is not a reason to leave a record out
  // Clear matches are for confirming in bulk, so records far from their label's range start left out
  function def(lv){return lv===1?-1:0;}
  function pass(i,lv){var o=lv===S.lv?S.o:def(lv);return !o||(o>0?far(i):near(i));}
  function two(i,lv){var l=(lv===2||lv===5)&&ctx.look(i);return l&&bits(l)?l:null;}
  function box(){
    if(BOX)return BOX;
    var x0=1e9,x1=-1e9,y0=1e9,y1=-1e9;
    D.grid.forEach(function(g){for(var k=0;k<g.length;k+=2){x0=Math.min(x0,g[k]);x1=Math.max(x1,g[k]);
      y0=Math.min(y0,g[k+1]);y1=Math.max(y1,g[k+1]);}});
    return(BOX={x0:x0,y0:y0,w:(x1-x0)*KX,h:y1-y0});
  }
  // The BC outline: grid edges no other cell shares (vertices are rounded, so shared ones match).
  function outline(){
    if(OUTL)return OUTL;
    var c={},e=[];
    D.grid.forEach(function(g){for(var k=0,m=g.length;k<m;k+=2){var j=(k+2)%m,
      a=g[k]+','+g[k+1],b=g[j]+','+g[j+1],key=a<b?a+'|'+b:b+'|'+a;
      c[key]=c[key]?c[key]+1:1;if(c[key]===1)e.push([key,g[k],g[k+1],g[j],g[j+1]]);}});
    return(OUTL=e.filter(function(x){return c[x[0]]===1;}));
  }
  function cellAt(i){
    var x=P.lonlat[2*i]*1000,y=P.lonlat[2*i+1]*1000;
    for(var c=0;c<D.grid.length;c++)if(inside(D.grid[c],x,y))return c;
    return -1;
  }
  // What the map says about the record's point, as words (caption and aria-label).
  function mapText(i,lv){
    var a=ctx.name(i),b=two(i,lv),t=!!b;
    if(OKM[i]===NONE)return{aria:'Range map of '+a+(t?' and '+b:'')+' in British Columbia',cap:''};
    var la=OKM[i]===0,lb=t&&has(bits(b),cellAt(i)),f=far(i),cap=[];
    if(f)cap.push('About '+kmText(i)+" km outside the label's usual range.");
    else if(t&&!la&&!lb)cap.push(NEITHER);
    else if(!la)cap.push("Outside the label's usual range.");
    if(f&&t&&lb)cap.push("Inside the look-alike's.");
    if(f&&t&&!lb)cap.push(NEITHER);
    return{aria:'Range map: this record is '+(la?'inside':'outside')+' the range of '+a+
      (t?', '+(lb?'inside':'outside')+' the range of '+b:'')+(cap.length?'. '+cap.join(' '):''),cap:cap.join(' ')};
  }
  function drawMap(cv,i,lv){
    var r=cv.getBoundingClientRect(),dpr=window.devicePixelRatio||1,B=box(),b=two(i,lv);
    if(!r.width)return;
    cv.width=Math.round(r.width*dpr);cv.height=Math.round(r.height*dpr);
    var g=cv.getContext('2d'),st=getComputedStyle(cv),pad=2*dpr,k=(cv.width-2*pad)/B.w;
    function X(v){return pad+(v-B.x0)*KX*k;}
    function Y(v){return cv.height-pad-(v-B.y0)*k;}
    function col(c){return st.getPropertyValue(c);}
    var A=bits(ctx.name(i)),L=b?bits(b):A;
    g.lineWidth=dpr*.5;g.lineJoin='round';
    D.grid.forEach(function(p,c){
      var a=has(A,c),l=has(L,c);
      g.fillStyle=g.strokeStyle=col(a?(b&&l?'--rboth':'--rlab'):l?'--rlook':'--line');
      g.beginPath();
      for(var q=0;q<p.length;q+=2)g[q?'lineTo':'moveTo'](X(p[q]),Y(p[q+1]));
      g.closePath();g.fill();g.stroke();});
    g.strokeStyle=col('--muted');g.lineWidth=dpr;g.beginPath();
    outline().forEach(function(e){g.moveTo(X(e[1]),Y(e[2]));g.lineTo(X(e[3]),Y(e[4]));});g.stroke();
    var px=X(P.lonlat[2*i]*1000),py=Y(P.lonlat[2*i+1]*1000);
    g.font=10*dpr+'px system-ui,sans-serif';g.textBaseline='middle';g.fillStyle=col('--muted');
    REFS.forEach(function(x){
      var rx=X(x[1]),ry=Y(x[2]);
      g.beginPath();g.arc(rx,ry,2*dpr,0,7);g.fill();
      if(Math.hypot(rx-px,ry-py)>15*dpr)g.fillText(x[0],rx+4*dpr,ry);});
    g.beginPath();g.arc(px,py,5*dpr,0,7);g.fillStyle='#fff';g.fill();
    g.beginPath();g.arc(px,py,3.2*dpr,0,7);g.fillStyle='#111';g.fill();
  }
  // The chip on a card: the verdict in a few words.
  function verdict(i,lv){
    if(lv===2&&NOTE[i]!==NONE){var t=D.notes[NOTE[i]].replace('Range: ','');
      return t.charAt(0).toUpperCase()+t.slice(1).replace('both ranges','both ranges: maybe neither');}
    if(far(i))return 'About '+kmText(i)+' km outside';
    return OKM[i]===NONE?'Range map':OKM[i]===0?'In range':'Just outside range';
  }
  function popEl(){
    if(pop)return pop;
    pop=el('div','rpop');pop.id='rpop';pop.setAttribute('role','dialog');pop.hidden=true;
    pop.setAttribute('aria-label','Range map');pop.tabIndex=-1;
    var x=el('button','rx','×');x.type='button';x.setAttribute('aria-label','Close range map');
    x.onclick=function(){closePop(true);};
    pop.append(x,el('canvas'),el('ul','rleg'),el('p','rcap'));
    pop.onmouseenter=function(){clearTimeout(Q.t);};
    pop.onmouseleave=leave;
    document.body.appendChild(pop);return pop;
  }
  function openPop(chip,i,lv,pinned,kb){
    clearTimeout(Q.t);
    if(Q.chip&&Q.chip!==chip)Q.chip.setAttribute('aria-expanded','false');
    var p=popEl(),cv=p.children[1],lg=p.children[2],t=mapText(i,lv),b=two(i,lv),a=ctx.name(i);
    Q={i:i,lv:lv,chip:chip,pin:pinned,t:0};
    chip.setAttribute('aria-expanded','true');
    cv.setAttribute('role','img');cv.setAttribute('aria-label',t.aria);
    cv.style.aspectRatio=box().w+'/'+box().h;
    lg.textContent='';
    (b?[['lab',a,1],['look',b,1],['both','both']]:[['lab',a,1]]).concat([[null,'this record']]).forEach(function(x){
      var li=el('li');li.appendChild(x[0]?el('span','sw '+x[0]):el('span','sw dot'));
      li.appendChild(x[2]?el('i',null,x[1]):document.createTextNode(x[1]));lg.appendChild(li);});
    p.children[3].textContent=t.cap;p.children[3].hidden=!t.cap;
    p.hidden=false;
    if(innerWidth>=600||matchMedia('(hover:hover)').matches){var r=chip.getBoundingClientRect(),w=p.offsetWidth,h=p.offsetHeight;
      p.style.left=Math.max(8,Math.min(r.left,innerWidth-w-8))+'px';
      p.style.top=(r.bottom+h+12>innerHeight&&r.top>h+12?r.top-h-6:r.bottom+6)+'px';}
    else{p.style.left=p.style.top='';}
    drawMap(cv,i,lv);
    if(kb)p.focus();
  }
  function closePop(refocus){
    if(!pop||pop.hidden)return;
    clearTimeout(Q.t);pop.hidden=true;Q.chip.setAttribute('aria-expanded','false');
    if(refocus)Q.chip.focus();
    Q.chip=null;
  }
  function leave(){
    clearTimeout(Q.t);
    if(Q.chip&&!Q.pin)Q.t=setTimeout(function(){closePop(false);},200);
  }
  function chip(i,lv){
    var b=el('button','rchip'),v=verdict(i,lv);
    b.type='button';b.setAttribute('aria-haspopup','dialog');b.setAttribute('aria-expanded','false');
    b.setAttribute('aria-controls','rpop');b.append(pin(),el('span',null,v));
    if(v!=='In range'&&v!=='Range map')b.classList.add('bad');
    b.onclick=function(e){
      if(Q.chip===b&&!pop.hidden&&(Q.pin||e.detail===0)){closePop(e.detail===0);return;}
      openPop(b,i,lv,true,e.detail===0);};
    b.onmouseenter=function(){
      if(!matchMedia('(hover:hover)').matches)return;
      clearTimeout(Q.t);if(Q.chip===b)return;
      Q.t=setTimeout(function(){openPop(b,i,lv,false,false);},300);};
    b.onmouseleave=leave;
    return b;
  }
  addEventListener('keydown',function(e){if(e.key==='Escape')closePop(true);});
  addEventListener('pointerdown',function(e){
    if(pop&&!pop.hidden&&!pop.contains(e.target)&&!(Q.chip&&Q.chip.contains(e.target)))closePop(false);});
  matchMedia('(prefers-color-scheme:dark)').addEventListener('change',function(){
    if(pop&&!pop.hidden)drawMap(pop.children[1],Q.i,Q.lv);});
  // The toggle state is kept in the hash under out=, only when it is not the level's default.
  function hash(){
    var t=location.hash.slice(1).split('&').filter(function(x){return x&&x.indexOf('out=')!==0;});
    if(S.o!==def(S.lv))t.push('out='+S.o);
    history.replaceState(null,'','#'+t.join('&'));
  }
  var OPTS=[[0,'All'],[-1,'Hide far outside'],[1,'Only far outside']],SEG=null;
  function seg(){
    var g=$('rout');
    if(!g)return null;
    var r=el('div','seg');r.setAttribute('role','radiogroup');r.setAttribute('aria-label','Records far outside their range');
    OPTS.forEach(function(x){
      var b=el('button','segb');b.type='button';b.setAttribute('role','radio');
      b.onclick=function(){S.o=x[0];hash();ctx.redraw();};
      r.appendChild(b);});
    r.onkeydown=function(e){
      var k=['ArrowLeft','ArrowUp','ArrowRight','ArrowDown','Home','End'].indexOf(e.key),
        all=[].filter.call(r.children,function(b){return !b.disabled;}),at=all.indexOf(document.activeElement);
      if(k<0||at<0)return;e.preventDefault();
      var to=k===4?0:k===5?all.length-1:(at+(k%4<2?-1:1)+all.length)%all.length;
      all[to].focus();all[to].click();
    };
    g.append(r,el('span','segnote','Far outside: '+OUT_KM+" km or more from the labelled species' known range in BC. "+
      'Records with no range map count as in range.'));
    return r;
  }
  SEG=seg();
  return {
    pass:pass,
    // the chip alone, or null when the label's range is unknown; close drops its popover
    chip:function(i,lv){return bits(ctx.name(i))?chip(i,lv):null;},
    close:function(){closePop(false);},
    // the chosen level, with the toggle out of the hash on load and at the level's default after
    level:function(lv,fromHash){
      var m=fromHash&&/(?:^|&)out=(-1|0|1)(?:&|$)/.exec(location.hash.slice(1));
      S.lv=lv;S.o=m?+m[1]:def(lv);hash();
    },
    // beside Identify, the range chip, or why there is none
    links:function(a,i,lv){
      var row=el('div','links');row.appendChild(a);
      if(bits(ctx.name(i)))row.appendChild(chip(i,lv));
      else if(lv===2&&NOTE[i]!==NONE)row.appendChild(el('span','range',D.notes[NOTE[i]]));
      else row.appendChild(el('span','range','No range map: range unknown'));
      return row;
    },
    // the control and its counts, over the selected records of the level
    draw:function(lv,sel,level){
      if(!SEG)return;
      var f=0,t=0;
      for(var i=0;i<n;i++)if(sel[i]&&level[i]===lv){t++;if(far(i))f++;}
      closePop(false);
      $('rout').hidden=false;
      var c={0:t,'-1':t-f,1:f};
      [].forEach.call(SEG.children,function(b,k){
        var o=OPTS[k][0],on=o===S.o;
        b.textContent=OPTS[k][1]+' '+c[o].toLocaleString('en');
        b.setAttribute('aria-checked',String(on));b.tabIndex=on?0:-1;
        b.disabled=o===1&&!f&&!on;});
    }
  };
};
})();
