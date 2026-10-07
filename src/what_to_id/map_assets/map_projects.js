// Projects. pool-projects.bin (see map_projects.py) lists the records in each project of
// META.projects.list; each record gets a bitmask, bit k set when it is in project k. The viewer adds
// projects from a list; each added chip toggles between "in" and "not in", and with two or more "in"
// chips a switch says whether a record must be in any of them (OR) or in all (AND). "Not in" chips
// always exclude. Without the file the box stays hidden and nothing is filtered. The mask is one
// byte, so at most 8 projects.
function projDecode(buf,list){
  var u=new Uint8Array(buf),hn=new DataView(buf).getUint32(0,true),o=4+hn,
    head=JSON.parse(new TextDecoder().decode(u.subarray(4,o))).projects,out=list.map(function(){return null;});
  head.forEach(function(p){
    var n=p.n,k=list.map(function(x){return x.id;}).indexOf(p.id);
    if(o+4*n>u.length)throw new Error('project file is cut short');
    if(k>=0){var a=new Uint32Array(n),s=0;
      for(var i=0;i<n;i++){s=(s+(u[o+i]|u[o+n+i]<<8|u[o+2*n+i]<<16|u[o+3*n+i]<<24))>>>0;a[i]=s;}out[k]=a;}
    o+=4*n;});
  if(o!==u.length)throw new Error('project file size does not match its header');
  return out;
}
// Sets bit k of mask[i] for records a..b-1 in lists[k]. Records arrive in shards, each sorted by id,
// so the range is walked run by run against each sorted list.
function projMask(id,lists,mask,a,b){
  for(var r=a;r<b;){var e=r+1;while(e<b&&id[e]>id[e-1])e++;
    for(var k=0;k<lists.length;k++){var L=lists[k];if(!L)continue;
      var lo=0,hi=L.length;while(lo<hi){var m=(lo+hi)>>1;if(L[m]<id[r])lo=m+1;else hi=m;}
      for(var i=r,j=lo;i<e&&j<L.length;i++){while(j<L.length&&L[j]<id[i])j++;if(L[j]===id[i])mask[i]|=1<<k;}}
    r=e;}
}
function projKeep(m,inc,exc,any){return !(m&exc)&&(!inc||(any?(m&inc)!==0:(m&inc)===inc));}
// The Identify parameters for a pick: iNaturalist ORs the ids in project_id and excludes those in
// not_in_project, so OR and NOT are exact. It cannot require several projects, so for AND it gets
// the smallest required project, a wider set than the map shows, and exact is false; the page then
// counts that set too and says so beside the Identify link.
function projParams(sel,any,list){
  var inc=sel.filter(function(s){return !s.not;}).map(function(s){return list[s.k];}),
    exc=sel.filter(function(s){return s.not;}).map(function(s){return list[s.k].id;}),q={},exact=true;
  if(exc.length)q.not_in_project=exc.join(',');
  if(inc.length>1&&!any){exact=false;inc=[inc.reduce(function(a,b){return b.n<a.n?b:a;})];}
  if(inc.length)q.project_id=inc.map(function(p){return p.id;}).join(',');
  return {q:q,exact:exact,widest:exact?null:list.indexOf(inc[0])};
}
// Each chip as a selection term, the shape a shared selection module can take over: mask() is 1 per
// record in the project, inat() its Identify parameters. Match all (AND) cannot be said on
// iNaturalist, so then the included terms are not exact.
function projTerms(sel,any,list,mask){
  var nInc=sel.filter(function(s){return !s.not;}).length;
  return sel.map(function(s){var p=list[s.k];return {dim:'project',kind:'project',id:p.id,label:p.title,
    exclude:s.not,mask:function(){var m=new Uint8Array(mask.length);
      for(var i=0;i<m.length;i++)m[i]=mask[i]>>s.k&1;return m;},
    inat:function(){var q={};q[s.not?'not_in_project':'project_id']=String(p.id);
      return {params:q,exact:s.not||any||nInc<2};}};});
}
function projectFilter(o){
  var meta=o.meta,list=(meta.projects&&meta.projects.list)||[],box=document.getElementById('projbox'),
    sel=[],any=true,lists=null,mask=new Uint8Array(0),key=0,inc=0,exc=0,shown=null,alt=0,
    nf=new Intl.NumberFormat('en-CA');
  (o.hash.get('projects')||'').split(',').forEach(function(t){
    var not=t.charAt(0)==='-',id=+(not?t.slice(1):t),k=list.map(function(p){return p.id;}).indexOf(id);
    if(t&&k>=0&&!sel.some(function(s){return s.k===k;}))sel.push({k:k,not:not});});
  any=o.hash.get('match')!=='all';
  function bits(){inc=exc=0;if(!lists)return;
    sel.forEach(function(s){if(s.not)exc|=1<<s.k;else inc|=1<<s.k;});}
  function el(tag,cls,text){var e=document.createElement(tag);if(cls)e.className=cls;
    if(text!=null)e.textContent=text;return e;}
  var pick,chips,seg,hint;
  function words(){var i=sel.filter(function(s){return !s.not;}).map(function(s){return list[s.k].title;}),
      x=sel.filter(function(s){return s.not;}).map(function(s){return list[s.k].title;}),w='';
    if(i.length)w='Records in '+(i.length>1&&!any?'all of ':'')+i.join(any?' or ':' and ');
    if(x.length)w+=(w?', but not in ':'Records not in ')+x.join(' or ');
    return w?w+'.':'Add a project, then click its chip to switch between in and not in.';}
  // what Identify opens instead when it cannot say the pick, with both counts; '' when exact
  function inexact(){var p=lists&&projParams(sel,any,list);if(!p||p.exact)return '';
    return 'it cannot require more than one project, so it opens every record in '+list[p.widest].title+
      (shown!=null?', '+nf.format(alt)+' rather than the '+nf.format(shown)+' in all of them':'');}
  function draw(){
    chips.textContent='';
    sel.forEach(function(s,j){var p=list[s.k],c=el('span','pchip'+(s.not?' not':'')),
        t=el('button',null,(s.not?'Not in ':'In ')+p.title),x=el('button','x','×');
      t.type=x.type='button';t.title='Click to switch between in and not in';
      t.setAttribute('aria-label',p.title+': '+(s.not?'not in':'in')+'. Click to switch.');
      x.setAttribute('aria-label','Remove '+p.title);
      t.onclick=function(){s.not=!s.not;change();};x.onclick=function(){sel.splice(j,1);change();};
      c.appendChild(t);c.appendChild(x);chips.appendChild(c);});
    pick.textContent='';pick.appendChild(el('option',null,'Add a project…')).value='';
    list.forEach(function(p,k){if(!sel.some(function(s){return s.k===k;})){
      var op=pick.appendChild(el('option',null,p.title));op.value=k;}});
    pick.hidden=pick.options.length<2;
    seg.hidden=sel.filter(function(s){return !s.not;}).length<2;
    seg.children[0].setAttribute('aria-pressed',String(any));seg.children[1].setAttribute('aria-pressed',String(!any));
    hint.textContent=words();
  }
  function change(){bits();key++;draw();o.changed();}
  function build(){
    box.appendChild(el('p','lbl','Projects'));
    var row=box.appendChild(el('div','prow'));
    pick=row.appendChild(el('select','padd'));pick.setAttribute('aria-label','Add a project');
    pick.onchange=function(){if(pick.value!==''){sel.push({k:+pick.value,not:false});change();}};
    seg=row.appendChild(el('span','seg'));seg.setAttribute('role','group');
    seg.setAttribute('aria-label','Records must be in');
    [['any','Match any',true],['all','Match all',false]].forEach(function(m){
      var b=seg.appendChild(el('button',null,m[1]));b.type='button';
      b.title=m[2]?'In at least one of the "in" projects':'In every "in" project';
      b.onclick=function(){any=m[2];change();};});
    chips=box.appendChild(el('div','chips pchips'));chips.setAttribute('aria-label','Picked projects');
    hint=box.appendChild(el('p','muted'));
    draw();box.hidden=false;
  }
  return {
    load:function(get){if(!list.length||!box)return;
      get(meta.projects.file).then(function(buf){
        lists=projDecode(buf,list).map(function(L){return L||new Uint32Array(0);});
        mask=new Uint8Array(0);build();bits();key++;o.changed();})
      .catch(function(e){if(window.console)console.warn('Project filters are off: '+e.message);});},
    sync:function(P){if(!lists||mask.length===P.n)return;var m=new Uint8Array(P.n),a=Math.min(mask.length,P.n);
      m.set(mask.subarray(0,a));projMask(P.id,lists,m,a,P.n);mask=m;},
    drop:function(i){return (inc|exc)!==0&&!projKeep(mask[i],inc,exc,any);},
    key:function(){return key;},
    wide:function(){var p=lists&&projParams(sel,any,list);if(!p||p.exact)return null;var b=1<<p.widest;
      return function(i){return (mask[i]&b)!==0&&!(mask[i]&exc);};},
    note:function(n,a){shown=n;alt=a;},inexact:inexact,
    active:function(){return (inc|exc)!==0;},
    params:function(){return lists?projParams(sel,any,list).q:{};},
    terms:function(){return lists?projTerms(sel,any,list,mask):[];},any:function(){return any;},
    hash:function(){if(!sel.length)return '';
      return 'projects='+sel.map(function(s){return (s.not?'-':'')+list[s.k].id;}).join(',')+(any?'':'&match=all');},
    reset:function(){if(!sel.length)return;sel=[];any=true;bits();key++;if(lists)draw();}
  };
}
