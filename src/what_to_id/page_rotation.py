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
  }
  nextBtn.addEventListener('click', function(){
    var res = nextBatch(state, DATA, group);
    state = res.state;
    save();
    if (res.done) {
      doneMsg.hidden = false;
      nextBtn.disabled = true;
      return;
    }
    runnerCode.textContent = 'Batch ' + res.batchNumber;
    window.open(res.url, '_blank', 'noopener');
    if (leftInGroup(DATA, state, group) === 0) {
      doneMsg.hidden = false;
      nextBtn.disabled = true;
    }
  });
  changeGroup.addEventListener('click', function(ev){ ev.preventDefault(); renderPicker(); });
  if (group && groups.indexOf(group) !== -1) { renderRunner(); } else { renderPicker(); }
})();
""".strip()


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
    body = (
        '<p class="lede">Work through each batch in iNaturalist, then come back for the next '
        "one.</p>\n"
        '<section id="picker"><div class="cards" id="groupList"></div></section>\n'
        '<section id="runner" hidden>'
        '<p class="crumbs"><a href="#" id="changeGroup">Change group</a></p>'
        '<p class="runcode" id="runnerCode">Batch 0</p>'
        '<button class="nextbtn" id="nextBtn" type="button">Next batch</button>'
        '<p id="doneMsg" hidden>All batches in this group are done.</p>'
        "</section>\n"
    )
    script = (
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
