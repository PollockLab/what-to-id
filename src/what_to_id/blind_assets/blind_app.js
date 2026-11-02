(function () {
  var cfg = JSON.parse(document.getElementById("blind-data").textContent);
  var recs = cfg.records, K = "blind.";
  var $ = function (id) { return document.getElementById(id); };
  var get = function (k, d) { try { var v = localStorage.getItem(K + k); return v === null ? d : JSON.parse(v); } catch (e) { return d; } };
  var put = function (k, v) { localStorage.setItem(K + k, JSON.stringify(v)); };
  var login = get("login", ""), shown = 0, answered = null;
  var PLAIN = { Aves: "birds", Plantae: "plants", Fungi: "fungi", Insecta: "insects", Mammalia: "mammals",
    Reptilia: "reptiles", Amphibia: "amphibians", Actinopterygii: "ray-finned fishes", Mollusca: "molluscs",
    Arachnida: "spiders and kin", Animalia: "other animals" };

  // seeded Fisher-Yates: FNV-1a of the login seeds mulberry32, so a login always gets the same order
  function permutation(n, seed) {
    var h = 2166136261, i, a = [];
    for (i = 0; i < seed.length; i++) { h = Math.imul(h ^ seed.charCodeAt(i), 16777619); }
    var s = h >>> 0, rnd = function () {
      s = (s + 0x6D2B79F5) >>> 0; var t = s;
      t = Math.imul(t ^ (t >>> 15), t | 1); t ^= t + Math.imul(t ^ (t >>> 7), t | 61);
      return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
    };
    for (i = 0; i < n; i++) a.push(i);
    for (i = n - 1; i > 0; i--) { var j = Math.floor(rnd() * (i + 1)), x = a[i]; a[i] = a[j]; a[j] = x; }
    return a;
  }
  function order() {
    var o = get("order." + login, null);
    if (!o || o.length !== recs.length) { o = permutation(recs.length, login); put("order." + login, o); }
    return o;
  }
  var mine = function () { return get("answers", []).filter(function (a) { return a.login === login; }); };

  function show(view) {
    ["login-view", "record-view", "done-view"].forEach(function (v) { $(v).hidden = v !== view; });
  }
  function header() {
    $("who").hidden = !login;
    $("login-name").textContent = login;
    $("count").textContent = mine().length + " of " + recs.length + " answered";
    $("export").disabled = $("clear").disabled = !mine().length;
    $("clear").textContent = "Clear my answers";
  }
  function render() {
    header();
    if (!login) { show("login-view"); $("login").focus(); return; }
    var pos = get("pos." + login, 0);
    if (pos >= recs.length) { show("done-view"); return; }
    var r = recs[order()[pos]];
    show("record-view");
    $("group").textContent = r.group + (PLAIN[r.group] ? " (" + PLAIN[r.group] + ")" : "");
    $("photo-hint").textContent = r.photos.length > 1 ? r.photos.length + " photos. Tap a small photo to see it large." : "";
    var main = $("main-photo");
    main.src = r.photos[0] || ""; main.alt = "Photo 1 of " + r.photos.length;
    $("thumbs").textContent = "";
    r.photos.forEach(function (u, i) {
      if (!i) return;
      var b = document.createElement("button"), im = document.createElement("img");
      b.type = "button"; b.setAttribute("aria-label", "Show photo " + (i + 1));
      im.src = u; im.alt = ""; b.appendChild(im);
      b.onclick = function () { main.src = u; main.alt = "Photo " + (i + 1) + " of " + r.photos.length; };
      $("thumbs").appendChild(b);
    });
    $("answer").reset();
    answered = mine().filter(function (a) { return a.record_id === r.id; })[0] || null;
    $("answer").hidden = !!answered; $("reveal").hidden = !answered;
    if (answered) $("mine").textContent = answered.taxon ? answered.taxon + " (" + answered.confidence + ")" : "I cannot say";
    $("link").href = cfg.obs + r.id;
    shown = Date.now();
    (answered ? $("next") : $("taxon")).focus();
  }
  function save(taxon, confidence) {
    var r = recs[order()[get("pos." + login, 0)]], all = get("answers", []);
    all.push({ record_id: r.id, login: login, taxon: taxon, confidence: confidence,
      seconds: Math.round((Date.now() - shown) / 100) / 10, saved_at: new Date().toISOString() });
    put("answers", all);  // reveal only after this write
    render();
  }

  $("answer").onsubmit = function (e) {
    e.preventDefault();
    var taxon = $("taxon").value.trim();
    if (!taxon) { $("taxon").focus(); return; }
    save(taxon, document.querySelector("input[name=conf]:checked").value);
  };
  $("abstain").onclick = function () { save("", "abstain"); };
  $("next").onclick = function () { put("pos." + login, get("pos." + login, 0) + 1); render(); };
  $("login-form").onsubmit = function (e) {
    e.preventDefault();
    var v = $("login").value.trim();
    if (!v) return;
    login = v; put("login", login); render();
  };
  $("change").onclick = function () { show("login-view"); $("login").value = login; $("login").focus(); };
  $("export").onclick = function () {
    var text = mine().map(function (a) { return JSON.stringify(a); }).join("\n") + "\n";
    var a = document.createElement("a");
    a.href = URL.createObjectURL(new Blob([text], { type: "application/x-ndjson" }));
    a.download = "blind-answers-" + login + ".jsonl";
    document.body.appendChild(a); a.click(); a.remove();
  };
  $("clear").onclick = function () {
    if ($("clear").textContent === "Clear my answers") { $("clear").textContent = "Really clear? Click again"; return; }
    put("answers", get("answers", []).filter(function (a) { return a.login !== login; }));
    put("pos." + login, 0); render();
  };
  $("clear").onblur = function () { $("clear").textContent = "Clear my answers"; };
  if (recs.length) render();
})();
