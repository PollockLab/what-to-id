// Sign in with iNaturalist (OAuth with PKCE, a public client) so a card can post an identification as the viewer.
// IdentifyInat(cfg), cfg {client, redirect} from page_identify (INAT_CLIENT_ID, INAT_REDIRECT); no client, no sign in.
// The redirect page (identify.html) trades the code for an access token, the token for an API token (a JWT), and keeps
// only the JWT and the user's id and login, in sessionStorage, for this tab. Nothing here logs a token.
var IdentifyInat=(function(){
'use strict';
var WWW='https://www.inaturalist.org',API='https://api.inaturalist.org/v1/',KEY='wtid-inat',FLOW='wtid-inat-flow';
function get(k){try{return JSON.parse(sessionStorage.getItem(k));}catch(e){return null;}}
function put(k,v){try{if(v==null)sessionStorage.removeItem(k);else sessionStorage.setItem(k,JSON.stringify(v));}catch(e){}}
function b64(bytes){return btoa(String.fromCharCode.apply(null,new Uint8Array(bytes))).replace(/\+/g,'-').replace(/\//g,'_').replace(/=+$/,'');}
function random(){return b64(crypto.getRandomValues(new Uint8Array(32)));}
function ok(r){if(!r.ok)throw new Error('iNaturalist answered '+r.status);return r.json();}
return function(cfg){
  var on=!!(cfg&&cfg.client&&window.crypto&&crypto.subtle);
  // Explore holds this page in a frame: the sign in leaves and comes back to the whole page.
  function start(){
    var verifier=random(),state=random(),top;
    try{top=window.top.location.href;}catch(e){top=location.href;}
    put(FLOW,{verifier:verifier,state:state,back:top});
    return crypto.subtle.digest('SHA-256',new TextEncoder().encode(verifier)).then(function(h){
      var q=new URLSearchParams({client_id:cfg.client,redirect_uri:cfg.redirect,response_type:'code',
        code_challenge:b64(h),code_challenge_method:'S256',state:state});
      window.top.location.href=WWW+'/oauth/authorize?'+q;
    });
  }
  // On the redirect: a code and our state in the query. Resolves true when it handled one (the page then leaves).
  function finish(){
    var q=new URLSearchParams(location.search),f=get(FLOW),code=q.get('code');
    if(!on||!code||!f||q.get('state')!==f.state)return Promise.resolve(false);
    put(FLOW,null);
    return fetch(WWW+'/oauth/token',{method:'POST',body:new URLSearchParams({client_id:cfg.client,code:code,
      redirect_uri:cfg.redirect,grant_type:'authorization_code',code_verifier:f.verifier})}).then(ok)
      .then(function(t){return fetch(WWW+'/users/api_token',{headers:{Authorization:'Bearer '+t.access_token}}).then(ok);})
      .then(function(j){return fetch(API+'users/me',{headers:{Authorization:j.api_token}}).then(ok).then(function(me){
        var u=me.results[0];put(KEY,{jwt:j.api_token,user:{id:u.id,login:u.login}});});})
      .catch(function(){put(KEY,null);})  // a failed sign in leaves the viewer signed out, on the Identify links
      .then(function(){location.replace(f.back);return true;});
  }
  function user(){var s=get(KEY);return s&&s.user||null;}
  // POST /v1/identifications as the viewer; an expired token signs them out.
  function identify(obs,taxon){
    var s=get(KEY);if(!s)return Promise.reject(new Error('Not signed in'));
    return fetch(API+'identifications',{method:'POST',headers:{Authorization:s.jwt,'Content-Type':'application/json'},
      body:JSON.stringify({identification:{observation_id:obs,taxon_id:taxon}})}).then(function(r){
        if(r.status===401)put(KEY,null);return ok(r);});
  }
  return {on:on,start:start,finish:finish,user:user,identify:identify,out:function(){put(KEY,null);}};
};
})();
