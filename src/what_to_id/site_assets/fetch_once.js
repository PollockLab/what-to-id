// fetchOnce(url): the bytes of one of the site's own data files as an ArrayBuffer, downloaded once.
// Explore's frames and the next page share a content-addressed file (name.<12 hex>.bin or a ?v= URL)
// through Cache Storage, a Web Lock per URL keeping two frames from fetching it at the same time;
// one page asking twice shares the promise. A non-ok answer rejects with Error(status).
var fetchOnce=(function(){
  var memo={},HASH=/^(.*)\.[0-9a-f]{12}(\.[^./]+)$/;
  function plain(u){return fetch(u).then(function(r){if(!r.ok)throw new Error(r.status);return r.arrayBuffer();});}
  // The cache key minus its hash or ?v=: a put drops the other versions of the same file.
  function stem(u){var x=new URL(u),m=x.pathname.match(HASH);
    if(m)return x.origin+m[1]+m[2];if(x.searchParams.has('v')){x.searchParams.delete('v');return x.href;}return null;}
  function shared(u){return navigator.locks.request('fetch:'+u,function(){
    return caches.open('wtid-data').then(function(c){return c.match(u).then(function(hit){
      if(hit)return hit.arrayBuffer();
      return fetch(u).then(function(r){if(!r.ok)throw new Error(r.status);
        var s=stem(u);
        return Promise.all([r.clone().arrayBuffer(),c.put(u,r).then(function(){return c.keys();}).then(function(ks){
          return Promise.all(ks.filter(function(k){return k.url!==u&&stem(k.url)===s;}).map(function(k){return c.delete(k);}));
        }).catch(function(){})]).then(function(a){return a[0];});});});});});}
  return function(url){
    var u=new URL(url,location.href).href;
    if(!memo[u]){
      var ok=window.caches&&navigator.locks&&new URL(u).origin===location.origin&&stem(u)!==null;
      memo[u]=(ok?shared(u).catch(function(e){if(/^\d+$/.test(e.message))throw e;return plain(u);}):plain(u))
        .catch(function(e){delete memo[u];throw e;});
    }
    return memo[u];
  };
})();
