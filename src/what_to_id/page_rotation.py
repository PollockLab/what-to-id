"""Rotation design: one blind index.html where every identifier cycles through all lists.

Unlike the "sets" design (page.py), no browser is stuck on one list: each click on "Next batch"
advances a per-browser, per-group cycle through the blind list labels in a random permutation
drawn once and stored in localStorage. Every label gets the same share of every identifier's
effort. Each browser also starts every list and group at its own random batch and wraps around,
so identifiers working the same group spread over the served window instead of all opening the
same first batches (disjoint dealing). The embedded data maps opaque list labels (the same
letters as manifest.arm_labels) to per-group ordered lists of Identify URLs; nothing else. No
arm name, batch_id, card fact, or thumbnail ever reaches this page.
"""

from __future__ import annotations

import json
from pathlib import Path

from what_to_id.manifest import Manifest
from what_to_id.page import ARM_WORDS, group_name
from what_to_id.page_style import CSS, FONTS

ROTATION_CSS = """
#groupList{display:flex;gap:.8rem;flex-wrap:wrap;margin:1.4rem 0}
.gbtn{flex:1 1 11rem;display:flex;flex-direction:column;gap:.1rem;padding:.9rem 1rem;
background:var(--card);color:var(--cink);border:1px solid var(--line);border-radius:12px;
font:inherit;text-align:left;cursor:pointer;box-shadow:0 6px 22px rgba(0,0,0,.5);
transition:border-color .12s}
.gbtn:hover{border-color:var(--acc)}
.gbtn b{font-size:1.1rem;color:var(--acc-ink);font-family:"Space Grotesk",Inter,system-ui,
sans-serif}
.gbtn span{color:var(--cmut);font-size:.9rem}
#runner{margin-top:1.4rem}
.runcode{font-family:"Space Grotesk",Inter,system-ui,sans-serif;font-size:1.3rem;font-weight:700;
color:var(--acc);margin:0 0 1rem}
.nextbtn{display:block;width:100%;padding:1.1rem;font-size:1.15rem;font-weight:700;
background:var(--gd);color:#062a12;border:0;border-radius:12px;cursor:pointer;
font-family:"Space Grotesk",Inter,system-ui,sans-serif;transition:filter .12s}
.nextbtn:hover{filter:brightness(1.08)}
.nextbtn:disabled{opacity:.5;cursor:default;filter:none}
#doneMsg{color:var(--mut);margin-top:1rem}
#runner .crumbs{display:flex;justify-content:space-between;align-items:center}
.linkbtn{background:none;border:0;padding:.2rem 0;font:inherit;font-size:.9rem;color:var(--mut);
cursor:pointer;transition:color .12s}
.linkbtn:hover{color:var(--acc)}
.linkbtn[hidden],.undo[hidden]{display:none}
.undo{display:flex;align-items:center;justify-content:space-between;gap:.8rem;margin-top:1rem;
padding:.7rem 1rem;background:var(--panel);border:1px solid #2a3a4d;border-radius:12px;
color:var(--ink)}
.undo .linkbtn{color:var(--acc);font-weight:700}
.flow{display:flex;align-items:center;gap:.6rem;margin:1.2rem 0 0}
.flow div{flex:1 1 0;display:flex;flex-direction:column;gap:.1rem;padding:.7rem .9rem;
background:var(--panel);border:1px solid #2a3a4d;border-radius:12px}
.flow b,.cycle .n{font-family:"Space Grotesk",Inter,system-ui,sans-serif;font-weight:700}
.flow span{color:var(--mut);font-size:.88rem}
.flow i,.cycle i{font-style:normal;color:var(--acc);font-size:1.2rem}
.cycle{display:flex;align-items:center;gap:.5rem;margin:.4rem 0 .8rem}
.how ul{margin:.3rem 0;padding-left:1.1rem}
.cycle .n{width:2.2rem;height:2.2rem;display:grid;place-items:center;border-radius:50%;
background:var(--card);color:var(--acc-ink)}
@media(max-width:44rem){.flow{flex-direction:column;align-items:stretch}
.flow i{align-self:center;transform:rotate(90deg)}}
""".strip()

# nextBatch is the one pure function driving the rotation: given the per-browser state, the
# embedded label -> group -> urls data, and the chosen group, it returns the next url (or done)
# and a new state. It never mutates its inputs, so it can be unit-tested outside the browser.
ROTATION_JS = """
function nextBatch(state, data, group) {
  var perm = state.perm, K = perm.length;
  var progress = state.progress || {};
  var prev = progress[group] || {step: 0, pointers: {}, served: 0};
  var pointers = Object.assign({}, prev.pointers);
  var attempt, label, idx, list, foundLabel = null, foundIdx = -1;
  for (attempt = 0; attempt < K; attempt++) {
    label = perm[(prev.step + attempt) % K];
    idx = pointers[label] || 0;
    list = (data[label] && data[label][group]) || [];
    if (idx < list.length) { foundLabel = label; foundIdx = idx; break; }
  }
  var next = Object.assign({}, progress);
  if (foundLabel === null) {
    next[group] = {step: prev.step + K, pointers: pointers, served: prev.served};
    return {
      state: Object.assign({}, state, {progress: next}),
      url: null, label: null, done: true, batchNumber: prev.served
    };
  }
  pointers[foundLabel] = foundIdx + 1;
  var urls = data[foundLabel][group];
  var offset = ((state.offsets || {})[foundLabel] || {})[group] || 0;
  var served = prev.served + 1;
  next[group] = {step: prev.step + attempt + 1, pointers: pointers, served: served};
  return {
    state: Object.assign({}, state, {progress: next}),
    url: urls[(offset + foundIdx) % urls.length],
    label: foundLabel,
    done: false,
    batchNumber: served
  };
}
function leftInGroup(data, state, group) {
  var pointers = ((state.progress || {})[group] || {}).pointers || {};
  var left = 0;
  Object.keys(data).forEach(function(label){
    var list = (data[label] && data[label][group]) || [];
    left += Math.max(0, list.length - (pointers[label] || 0));
  });
  return left;
}
function startOver(state, group) {
  var progress = Object.assign({}, state.progress || {});
  delete progress[group];
  return Object.assign({}, state, {progress: progress});
}
(function(){
  var SKEY = 'what-to-id-rotation';
  var GKEY = 'what-to-id-rotation-group';
  var labels = Object.keys(DATA);
  var groups = [];
  labels.forEach(function(l){Object.keys(DATA[l]).forEach(function(g){
    if (groups.indexOf(g) === -1) groups.push(g);
  });});
  groups.sort();
  function shuffled(arr) {
    var a = arr.slice();
    for (var i = a.length - 1; i > 0; i--) {
      var j = Math.floor(Math.random() * (i + 1));
      var t = a[i]; a[i] = a[j]; a[j] = t;
    }
    return a;
  }
  var state = null;
  try { state = JSON.parse(localStorage.getItem(SKEY) || 'null'); } catch (e) {}
  if (!state || !Array.isArray(state.perm) || state.perm.length !== labels.length) {
    state = {perm: shuffled(labels), progress: {}};
  }
  // A new daily build re-cuts every list, so old pointers and offsets point at other batches.
  // Keep the browser's list cycle, start the batches afresh.
  if (state.build !== BUILD) {
    state = {perm: state.perm, progress: {}, build: BUILD};
  }
  if (!state.offsets) {
    state.offsets = {};
    labels.forEach(function(l){
      state.offsets[l] = {};
      Object.keys(DATA[l]).forEach(function(g){
        state.offsets[l][g] = Math.floor(Math.random() * DATA[l][g].length);
      });
    });
  }
  var group = null;
  try { group = localStorage.getItem(GKEY); } catch (e) {}
  function save() {
    try {
      localStorage.setItem(SKEY, JSON.stringify(state));
      if (group) localStorage.setItem(GKEY, group);
    } catch (e) {}
  }
  var picker = document.getElementById('picker');
  var runner = document.getElementById('runner');
  var groupList = document.getElementById('groupList');
  var runnerCode = document.getElementById('runnerCode');
  var nextBtn = document.getElementById('nextBtn');
  var doneMsg = document.getElementById('doneMsg');
  var changeGroup = document.getElementById('changeGroup');
  var startOverBtn = document.getElementById('startOver');
  var undoMsg = document.getElementById('undoMsg');
  var undoText = document.getElementById('undoText');
  var undoBtn = document.getElementById('undoBtn');
  var undoState = null, undoTimer = null;
  function hideUndo() { undoMsg.hidden = true; undoState = null; clearTimeout(undoTimer); }
  function renderPicker() {
    groupList.innerHTML = '';
    groups.forEach(function(g){
      var left = leftInGroup(DATA, state, g);
      var b = document.createElement('button');
      b.type = 'button';
      b.className = 'gbtn';
      b.innerHTML = '<b>' + (GROUP_NAMES[g] || g) + '</b><span>' + left + ' batches left</span>';
      b.addEventListener('click', function(){ group = g; save(); renderRunner(); });
      groupList.appendChild(b);
    });
    picker.hidden = false;
    runner.hidden = true;
  }
  function renderRunner() {
    picker.hidden = true;
    runner.hidden = false;
    var served = ((state.progress || {})[group] || {}).served || 0;
    runnerCode.textContent = 'Batch ' + served;
    var left = leftInGroup(DATA, state, group);
    doneMsg.hidden = left > 0;
    nextBtn.disabled = left === 0;
    startOverBtn.hidden = served === 0;
  }
  nextBtn.addEventListener('click', function(){
    hideUndo();
    var res = nextBatch(state, DATA, group);
    state = res.state;
    save();
    if (res.done) {
      doneMsg.hidden = false;
      nextBtn.disabled = true;
      return;
    }
    runnerCode.textContent = 'Batch ' + res.batchNumber;
    startOverBtn.hidden = false;
    window.open(res.url, '_blank', 'noopener');
    if (leftInGroup(DATA, state, group) === 0) {
      doneMsg.hidden = false;
      nextBtn.disabled = true;
    }
  });
  changeGroup.addEventListener('click', function(ev){
    ev.preventDefault(); hideUndo(); renderPicker();
  });
  // Start over puts this group's batches back, keeps the list cycle, and offers Undo for 10 s.
  startOverBtn.addEventListener('click', function(){
    undoState = state;
    state = startOver(state, group);
    save();
    renderRunner();
    undoText.textContent = 'Started over. All ' + leftInGroup(DATA, state, group) +
      ' batches in ' + (GROUP_NAMES[group] || group) + ' are back.';
    undoMsg.hidden = false;
    clearTimeout(undoTimer);
    undoTimer = setTimeout(hideUndo, 10000);
  });
  undoBtn.addEventListener('click', function(){
    if (undoState) { state = undoState; save(); renderRunner(); }
    hideUndo();
  });
  if (group && groups.indexOf(group) !== -1) { renderRunner(); } else { renderPicker(); }
})();
""".strip()


# Plain words for each order in the method section. Never the arm names, which ARM_WORDS guards.
ORDER_TEXT = {
    "recency": "<b>Newest first.</b> The control, close to what iNaturalist shows today.",
    "gap_first": "<b>Data-poor places first.</b> Records from areas with few or old records.",
    "similarity": "<b>Look-alike photos together.</b> Similar photos sit in the same batch.",
    "novelty": "<b>Unfamiliar photos first.</b> Photos least like any Research Grade photo.",
}


def _method(manifest: Manifest) -> str:
    """The test in five steps, with one line per order in this build."""
    missing = [a for a in manifest.arms if a not in ORDER_TEXT]
    if missing:
        raise ValueError(f"no page words for list order(s) {missing}; add them to ORDER_TEXT")
    orders = "".join(f"<li>{ORDER_TEXT[a]}</li>" for a in manifest.arms)
    steps = (
        "<b>The question.</b> Does the order of records change how many get an ID, and which?",
        "<b>The lists.</b> Each record goes to one list at random, so every list holds the same "
        f"mix of species and observers. Only the order is different:<ul>{orders}</ul>",
        "<b>Your batches.</b> Each press of Next batch takes the next list in turn. Your browser "
        "picks the turn order at random. The page does not say which list a batch is from.",
        "<b>The count.</b> After the blitz, we count each participant's species-level IDs on each "
        "list and compare each person with themself. A fast identifier adds the same to every "
        "list.",
        "<b>Nothing else changes.</b> You identify in iNaturalist as usual. Your IDs carry your "
        "name, count toward Research Grade and go to GBIF.",
    )
    items = "".join(f"<li>{s}</li>" for s in steps)
    return f'<section class="how"><h2>How the test works</h2><ol>{items}</ol></section>\n'


def _rotation_data(manifest: Manifest) -> dict[str, dict[str, list[str]]]:
    """label -> group -> ordered Identify URLs, in the order batches were cut."""
    data: dict[str, dict[str, list[str]]] = {}
    for _bid, b in sorted(manifest.batches.items()):
        label = manifest.arm_labels[b["arm"]]
        data.setdefault(label, {}).setdefault(str(b["group"]), []).append(b["url"])
    return data


def render_rotation_index(manifest: Manifest, *, title: str) -> str:
    """One blind page: pick a group, then cycle "Next batch" through the lists in equal share."""
    data = _rotation_data(manifest)
    groups = sorted({g for by_group in data.values() for g in by_group})
    group_names = {g: group_name(g) for g in groups}
    sub = (
        f"Records that needed an ID in British Columbia on {manifest.freeze}."
        if manifest.freeze
        else ""
    )
    sub_html = f'<p class="sub">{sub}</p>\n' if sub else ""
    arrow = '<i aria-hidden="true">&rarr;</i>'
    steps = (
        ("Pick a group", "one you know"),
        ("Next batch", f"up to {int(manifest.batch_size)} records open in iNaturalist"),
        ("ID what you can", "skip the rest, then come back"),
    )
    flow = arrow.join(f"<div><b>{b}</b><span>{s}</span></div>" for b, s in steps)
    cycle = arrow.join(f'<span class="n">{i}</span>' for i in range(1, len(data) + 1))
    body = (
        f'<div class="flow">{flow}</div>\n'
        '<section id="picker"><div class="cards" id="groupList"></div></section>\n'
        '<section id="runner" hidden>'
        '<p class="crumbs"><a href="#" id="changeGroup">Change group</a>'
        '<button class="linkbtn" id="startOver" type="button" hidden>'
        "&#8634; Start over</button></p>"
        '<p class="runcode" id="runnerCode">Batch 0</p>'
        '<button class="nextbtn" id="nextBtn" type="button">Next batch</button>'
        '<p id="doneMsg" hidden>All batches in this group are done.</p>'
        '<p class="undo" id="undoMsg" aria-live="polite" hidden><span id="undoText"></span>'
        '<button class="linkbtn" id="undoBtn" type="button">Undo</button></p>'
        "</section>\n"
        f'<section class="why"><h2>{len(data)} lists, in turn</h2>'
        f'<div class="cycle" aria-hidden="true">{cycle}<i>&#8634;</i></div>'
        f"<p>Each press takes the next of {len(data)} lists, so your batches spread evenly over "
        "all of them.</p></section>\n"
        f"{_method(manifest)}"
    )
    script = (
        f"var BUILD={json.dumps(manifest.created_at)};"
        f"var DATA={json.dumps(data, sort_keys=True)};"
        f"var GROUP_NAMES={json.dumps(group_names, sort_keys=True)};"
        f"{ROTATION_JS}"
    )
    return (
        '<!doctype html>\n<html lang="en">\n<head>\n<meta charset="utf-8">\n'
        '<meta name="viewport" content="width=device-width,initial-scale=1">\n'
        f"<title>{title}</title>\n{FONTS}<style>{CSS}{ROTATION_CSS}</style>\n</head>\n<body>\n"
        f"<main>\n<h1>{title}</h1>\n{sub_html}{body}"
        f"</main>\n<script>{script}</script>\n</body>\n</html>\n"
    )


def write_rotation_site(out_dir: Path | str, manifest: Manifest) -> list[Path]:
    """Write a single blind index.html for the rotation design."""
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    html = render_rotation_index(manifest, title="What to ID next in BC")
    low = html.lower()
    for w in ARM_WORDS:
        if w in low:
            raise ValueError(f"index.html: arm name {w!r} leaked into the rotation page")
    path = out / "index.html"
    path.write_text(html)
    return [path]
