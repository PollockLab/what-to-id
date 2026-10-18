// Port of open_clip's SimpleTokenizer (CLIP BPE, clean='lower', context 77) for the browser text encoder.
// Cleaning mirrors open_clip's basic_clean: ftfy.fix_text (all fixers except mojibake repair and the
// non-HTML4 entity names), html.unescape twice, whitespace collapse, lowercase. The caller supplies the
// merges text (the text-encoder export writes it as bpe_merges.txt); fetching and decompressing is not done here.
var ClipTokenizer=(function(){
'use strict';
var CONTEXT=77,SOT=49406,EOT=49407,MERGES=49152-256-2+1-1;
// Python str.isspace() set, used by str.split()/strip() in open_clip.
var WS='\\t-\\r\\x1c-\\x20\\x85\\xa0\\u1680\\u2000-\\u200a\\u2028\\u2029\\u202f\\u205f\\u3000';
var WS_RUN=new RegExp('['+WS+']+','gu'),WS_EDGE=new RegExp('^['+WS+']+|['+WS+']+$','gu');
var PAT=/<start_of_text>|<end_of_text>|'s|'t|'re|'ve|'m|'ll|'d|\p{L}+|\p{N}|[^\s\p{L}\p{N}]+/giu;
// HTML4 entity names (html5 value for lang/rang) plus the unterminated legacy names html.unescape accepts.
var H4='AElig:c6,Aacute:c1,Acirc:c2,Agrave:c0,Alpha:391,Aring:c5,Atilde:c3,Auml:c4,Beta:392,Ccedil:c7,Chi:3a7,Dagger:2021,Delta:394,ETH:d0,Eacute:c9,Ecirc:ca,Egrave:c8,Epsilon:395,Eta:397,Euml:cb,Gamma:393,Iacute:cd,Icirc:ce,Igrave:cc,Iota:399,Iuml:cf,Kappa:39a,Lambda:39b,Mu:39c,Ntilde:d1,Nu:39d,OElig:152,Oacute:d3,Ocirc:d4,Ograve:d2,Omega:3a9,Omicron:39f,Oslash:d8,Otilde:d5,Ouml:d6,Phi:3a6,Pi:3a0,Prime:2033,Psi:3a8,Rho:3a1,Scaron:160,Sigma:3a3,THORN:de,Tau:3a4,Theta:398,Uacute:da,Ucirc:db,Ugrave:d9,Upsilon:3a5,Uuml:dc,Xi:39e,Yacute:dd,Yuml:178,Zeta:396,aacute:e1,acirc:e2,acute:b4,aelig:e6,agrave:e0,alefsym:2135,alpha:3b1,amp:26,and:2227,ang:2220,aring:e5,asymp:2248,atilde:e3,auml:e4,bdquo:201e,beta:3b2,brvbar:a6,bull:2022,cap:2229,ccedil:e7,cedil:b8,cent:a2,chi:3c7,circ:2c6,clubs:2663,cong:2245,copy:a9,crarr:21b5,cup:222a,curren:a4,dArr:21d3,dagger:2020,darr:2193,deg:b0,delta:3b4,diams:2666,divide:f7,eacute:e9,ecirc:ea,egrave:e8,empty:2205,emsp:2003,ensp:2002,epsilon:3b5,equiv:2261,eta:3b7,eth:f0,euml:eb,euro:20ac,exist:2203,fnof:192,forall:2200,frac12:bd,frac14:bc,frac34:be,frasl:2044,gamma:3b3,ge:2265,gt:3e,hArr:21d4,harr:2194,hearts:2665,hellip:2026,iacute:ed,icirc:ee,iexcl:a1,igrave:ec,image:2111,infin:221e,int:222b,iota:3b9,iquest:bf,isin:2208,iuml:ef,kappa:3ba,lArr:21d0,lambda:3bb,lang:27e8,laquo:ab,larr:2190,lceil:2308,ldquo:201c,le:2264,lfloor:230a,lowast:2217,loz:25ca,lrm:200e,lsaquo:2039,lsquo:2018,lt:3c,macr:af,mdash:2014,micro:b5,middot:b7,minus:2212,mu:3bc,nabla:2207,nbsp:a0,ndash:2013,ne:2260,ni:220b,not:ac,notin:2209,nsub:2284,ntilde:f1,nu:3bd,oacute:f3,ocirc:f4,oelig:153,ograve:f2,oline:203e,omega:3c9,omicron:3bf,oplus:2295,or:2228,ordf:aa,ordm:ba,oslash:f8,otilde:f5,otimes:2297,ouml:f6,para:b6,part:2202,permil:2030,perp:22a5,phi:3c6,pi:3c0,piv:3d6,plusmn:b1,pound:a3,prime:2032,prod:220f,prop:221d,psi:3c8,quot:22,rArr:21d2,radic:221a,rang:27e9,raquo:bb,rarr:2192,rceil:2309,rdquo:201d,real:211c,reg:ae,rfloor:230b,rho:3c1,rlm:200f,rsaquo:203a,rsquo:2019,sbquo:201a,scaron:161,sdot:22c5,sect:a7,shy:ad,sigma:3c3,sigmaf:3c2,sim:223c,spades:2660,sub:2282,sube:2286,sum:2211,sup:2283,sup1:b9,sup2:b2,sup3:b3,supe:2287,szlig:df,tau:3c4,there4:2234,theta:3b8,thetasym:3d1,thinsp:2009,thorn:fe,tilde:2dc,times:d7,trade:2122,uArr:21d1,uacute:fa,uarr:2191,ucirc:fb,ugrave:f9,uml:a8,upsih:3d2,upsilon:3c5,uuml:fc,weierp:2118,xi:3be,yacute:fd,yen:a5,yuml:ff,zeta:3b6,zwj:200d,zwnj:200c';
var LEGACY='AElig,AMP,Aacute,Acirc,Agrave,Aring,Atilde,Auml,COPY,Ccedil,ETH,Eacute,Ecirc,Egrave,Euml,GT,Iacute,Icirc,Igrave,Iuml,LT,Ntilde,Oacute,Ocirc,Ograve,Oslash,Otilde,Ouml,QUOT,REG,THORN,Uacute,Ucirc,Ugrave,Uuml,Yacute,aacute,acirc,acute,aelig,agrave,amp,aring,atilde,auml,brvbar,ccedil,cedil,cent,copy,curren,deg,divide,eacute,ecirc,egrave,eth,euml,frac12,frac14,frac34,gt,iacute,icirc,iexcl,igrave,iquest,iuml,laquo,lt,macr,micro,middot,nbsp,not,ntilde,oacute,ocirc,ograve,ordf,ordm,oslash,otilde,ouml,para,plusmn,pound,quot,raquo,reg,sect,shy,sup1,sup2,sup3,szlig,thorn,times,uacute,ucirc,ugrave,uml,uuml,yacute,yen,yuml'.split(',');
// Windows-1252 for the C1 range 0x80-0x9f (undefined slots stay as the control character).
var C1='\u20ac\x81\u201a\u0192\u201e\u2026\u2020\u2021\u02c6\u2030\u0160\u2039\u0152\x8d\u017d\x8f\x90\u2018\u2019\u201c\u201d\u2022\u2013\u2014\u02dc\u2122\u0161\u203a\u0153\x9d\u017e\u0178';
var ENT={},LEG={},LIGATURES={'\u0132':'IJ','\u0133':'ij','\u0149':'\u02bcn','\u01f1':'DZ','\u01f2':'Dz','\u01f3':'dz',
  '\u01c4':'D\u017d','\u01c5':'D\u017e','\u01c6':'d\u017e','\u01c7':'LJ','\u01c8':'Lj','\u01c9':'lj','\u01ca':'NJ',
  '\u01cb':'Nj','\u01cc':'nj','\ufb00':'ff','\ufb01':'fi','\ufb02':'fl','\ufb03':'ffi','\ufb04':'ffl',
  '\ufb05':'\u017ft','\ufb06':'st'};
H4.split(',').forEach(function(p){var i=p.indexOf(':');ENT[p.slice(0,i)]=parseInt(p.slice(i+1),16);});
LEGACY.forEach(function(n){LEG[n]=ENT[n]!==undefined?ENT[n]:ENT[n.toLowerCase()];});
// Python html.unescape: invalid code points are dropped or replaced as in CPython's html module.
function badCodepoint(n){
  return (n>=1&&n<=8)||n===11||(n>=14&&n<=31)||(n>=127&&n<=159)||(n>=0xfdd0&&n<=0xfdef)||
    (n&0xfffe)===0xfffe;
}
function charref(m,s){
  var n,t;
  if(s[0]==='#'){
    n=(s[1]==='x'||s[1]==='X')?parseInt(s.slice(2).replace(/;$/,''),16):parseInt(s.slice(1).replace(/;$/,''),10);
    if(n===0)return '\ufffd';
    if(n===13)return '\r';
    if(n>=128&&n<=159)return C1[n-128];
    if((n>=0xd800&&n<=0xdfff)||n>0x10ffff)return '\ufffd';
    return badCodepoint(n)?'':String.fromCodePoint(n);
  }
  if(s.slice(-1)===';'&&ENT.hasOwnProperty(s.slice(0,-1)))return String.fromCodePoint(ENT[s.slice(0,-1)]);
  if(s.slice(-1)!==';'&&LEG.hasOwnProperty(s))return String.fromCodePoint(LEG[s]);
  for(var x=s.length-1;x>1;x--){t=s.slice(0,x);
    if(LEG.hasOwnProperty(t))return String.fromCodePoint(LEG[t])+s.slice(x);}
  return '&'+s;
}
function htmlUnescape(text){
  return text.indexOf('&')<0?text:text.replace(/&(#[0-9]+;?|#[xX][0-9a-fA-F]+;?|[^\t\n\f <&#;]{1,32};?)/g,charref);
}
// ftfy.fix_text without mojibake repair (the entity step only runs when there is no "<", as in ftfy).
function fixText(text){
  var prev;
  do{
    prev=text;
    if(text.indexOf('<')<0)text=text.replace(/&([A-Za-z][A-Za-z0-9]*);/g,function(m,n){
      return ENT.hasOwnProperty(n)?String.fromCodePoint(ENT[n]):m;});
    text=text.replace(/[\x80-\x9f]/g,function(c){return C1[c.charCodeAt(0)-128];})
      .replace(/[\u0132\u0133\u0149\u01c4-\u01cc\u01f1-\u01f3\ufb00-\ufb06]/g,function(c){return LIGATURES[c];})
      .replace(/[\uff01-\uffef]/g,function(c){return c.normalize('NFKC');})
      .replace(/\u3000/g,' ')
      .replace(/[\u02bc\u2018-\u201b]/g,"'").replace(/[\u201c-\u201f]/g,'"')
      .replace(/\r\n|[\r\u2028\u2029\u0085]/g,'\n')
      .replace(/[\ud800-\udbff](?![\udc00-\udfff])|(?<![\ud800-\udbff])[\udc00-\udfff]/g,'\ufffd')
      .replace(/\x1b\[[0-9;]*[a-zA-Z]/g,'')
      .replace(/[\x00-\x08\x0b\x0e-\x1f\x7f\u206a-\u206f\ufeff\ufff9-\ufffc]/g,'')
      .normalize('NFC');
  }while(text!==prev);
  return text;
}
function strip(t){return t.replace(WS_EDGE,'');}
function basicClean(text){return strip(htmlUnescape(htmlUnescape(fixText(text))));}
function whitespaceClean(text){return strip(strip(text).replace(WS_RUN,' '));}
function clean(text){return whitespaceClean(basicClean(text)).toLowerCase();}
// GPT-2 byte-to-unicode table, as bytes_to_unicode() in open_clip.
var BYTE_ORDER=[],BYTE_ENC=(function(){
  var bs=[],cs=[],n=0,i;
  for(i=33;i<=126;i++)bs.push(i);
  for(i=161;i<=172;i++)bs.push(i);
  for(i=174;i<=255;i++)bs.push(i);
  cs=bs.slice();
  for(i=0;i<256;i++)if(bs.indexOf(i)<0){bs.push(i);cs.push(256+n);n++;}
  var t=new Array(256);
  for(i=0;i<bs.length;i++){t[bs[i]]=String.fromCharCode(cs[i]);BYTE_ORDER.push(t[bs[i]]);}
  return t;
})();
function create(mergesText,contextLength){
  if(typeof mergesText!=='string')throw new Error('CLIP BPE merges must be provided as text.');
  var lines=mergesText.split('\n').slice(1,1+MERGES);
  if(lines.length<MERGES)throw new Error('CLIP BPE merges are incomplete: expected '+MERGES+' lines after the header.');
  var vocab=[],ranks=new Map(),encoder=new Map(),cache=new Map(),ctx=contextLength||CONTEXT,i,j;
  for(i=0;i<256;i++)vocab.push(BYTE_ORDER[i]);
  for(i=0;i<256;i++)vocab.push(BYTE_ORDER[i]+'</w>');
  for(i=0;i<lines.length;i++){
    var p=lines[i].trim().split(/\s+/);
    ranks.set(p[0]+' '+p[1],i);vocab.push(p[0]+p[1]);
  }
  vocab.push('<start_of_text>','<end_of_text>');
  for(i=0;i<vocab.length;i++)encoder.set(vocab[i],i);
  cache.set('<start_of_text>','<start_of_text>');cache.set('<end_of_text>','<end_of_text>');
  var utf8=new TextEncoder();
  function pairs(word){var s=new Set();for(var k=0;k<word.length-1;k++)s.add(word[k]+' '+word[k+1]);return s;}
  function bpe(token){
    if(cache.has(token))return cache.get(token);
    var word=Array.from(token);
    word[word.length-1]+='</w>';
    var ps=pairs(word);
    if(ps.size===0)return token+'</w>';
    while(true){
      var best=null,rank=Infinity;
      ps.forEach(function(pr){var r=ranks.get(pr);if(r!==undefined&&r<rank){rank=r;best=pr;}});
      if(best===null)break;
      var sp=best.split(' '),first=sp[0],second=sp[1],nw=[];
      i=0;
      while(i<word.length){
        j=word.indexOf(first,i);
        if(j<0){for(;i<word.length;i++)nw.push(word[i]);break;}
        for(;i<j;i++)nw.push(word[i]);
        if(word[i]===first&&i<word.length-1&&word[i+1]===second){nw.push(first+second);i+=2;}
        else{nw.push(word[i]);i++;}
      }
      word=nw;
      if(word.length===1)break;
      ps=pairs(word);
    }
    var out=word.join(' ');
    cache.set(token,out);
    return out;
  }
  function encode(text){
    var out=[],toks=clean(text).match(PAT)||[];
    toks.forEach(function(tok){
      var mapped='',bytes=utf8.encode(tok);
      for(var k=0;k<bytes.length;k++)mapped+=BYTE_ENC[bytes[k]];
      bpe(mapped).split(' ').forEach(function(b){out.push(encoder.get(b));});
    });
    return out;
  }
  // [sot, ...ids, eot] zero-padded to the context length; over-long input is cut with eot kept last.
  function tokenize(text){
    var t=[SOT].concat(encode(text),[EOT]),res=new Array(ctx).fill(0);
    if(t.length>ctx){t=t.slice(0,ctx);t[ctx-1]=EOT;}
    for(var k=0;k<t.length;k++)res[k]=t[k];
    return res;
  }
  function tokenizeBatch(texts){return texts.map(tokenize);}
  return {encode:encode,tokenize:tokenize,tokenizeBatch:tokenizeBatch,contextLength:ctx,vocabSize:vocab.length};
}
return {CONTEXT:CONTEXT,SOT:SOT,EOT:EOT,MERGES:MERGES,create:create,clean:clean,basicClean:basicClean,
  fixText:fixText,htmlUnescape:htmlUnescape,whitespaceClean:whitespaceClean};
})();
if(typeof module!=='undefined'&&module.exports)module.exports=ClipTokenizer;
