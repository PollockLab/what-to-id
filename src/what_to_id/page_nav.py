"""Site header and view switcher shared by every published page. Stdlib only.

scripts/atlas_page.sh runs on a bare python3, so this must not import numpy, pandas or page_map.
`CSS` holds the colour tokens and the shell rules; `nav` returns the skip link, the header and the
script that points the switcher at what the viewer has open, then the toggletips (`explain`).
"""

from __future__ import annotations

import json
from html import escape
from pathlib import Path

from what_to_id.glossary import GLOSSARY

# (file, label), one tab per job: Identify, Confused pairs (confusion.html), then Methods.
# Identify holds the map, the photo space and the taxonomy behind its What and Where panels, as
# the full-screen explore.html; that page and map.html, embeddings.html, tree.html and
# search.html keep their URLs and mark Identify as current. Without identify.html the Identify
# tab falls back to the map. Confused pairs exists only
# when the atlas manifest lists its table. The brand links to index.html, a copy of the landing
# page.
PAGES = (
    ("identify.html", "Identify"),
    ("confusion.html", "Confused pairs"),
    ("terms.html", "How it works"),
)
OPTIONAL = {"confusion.html"}
EXPLORE = "identify.html"
BLITZ = "https://pollocklab.github.io/where-to-blitz/"
SITE = ("https://openbiodiversity.ca/", "openbiodiversity.ca")  # the top-right link
# the site's contour mark, inlined (64x44 PNG) because pages are self-contained
SITE_MARK = (
    "data:image/png;base64,"
    "iVBORw0KGgoAAAANSUhEUgAAAEAAAAAsCAYAAADVX77/AAAABGdBTUEAALGPC/xhBQAAACBjSFJNAAB6JgAAgIQA"
    "APoAAACA6AAAdTAAAOpgAAA6mAAAF3CculE8AAAAeGVYSWZNTQAqAAAACAAEARoABQAAAAEAAAA+ARsABQAAAAEA"
    "AABGASgAAwAAAAEAAgAAh2kABAAAAAEAAABOAAAAAAAAAGAAAAABAAAAYAAAAAEAA6ABAAMAAAABAAEAAKACAAQA"
    "AAABAAAAQKADAAQAAAABAAAALAAAAADGQQAMAAAACXBIWXMAAA7EAAAOxAGVKw4bAAACmmlUWHRYTUw6Y29tLmFk"
    "b2JlLnhtcAAAAAAAPHg6eG1wbWV0YSB4bWxuczp4PSJhZG9iZTpuczptZXRhLyIgeDp4bXB0az0iWE1QIENvcmUg"
    "Ni4wLjAiPgogICA8cmRmOlJERiB4bWxuczpyZGY9Imh0dHA6Ly93d3cudzMub3JnLzE5OTkvMDIvMjItcmRmLXN5"
    "bnRheC1ucyMiPgogICAgICA8cmRmOkRlc2NyaXB0aW9uIHJkZjphYm91dD0iIgogICAgICAgICAgICB4bWxuczp0"
    "aWZmPSJodHRwOi8vbnMuYWRvYmUuY29tL3RpZmYvMS4wLyIKICAgICAgICAgICAgeG1sbnM6ZXhpZj0iaHR0cDov"
    "L25zLmFkb2JlLmNvbS9leGlmLzEuMC8iPgogICAgICAgICA8dGlmZjpYUmVzb2x1dGlvbj45NjwvdGlmZjpYUmVz"
    "b2x1dGlvbj4KICAgICAgICAgPHRpZmY6WVJlc29sdXRpb24+OTY8L3RpZmY6WVJlc29sdXRpb24+CiAgICAgICAg"
    "IDx0aWZmOlJlc29sdXRpb25Vbml0PjI8L3RpZmY6UmVzb2x1dGlvblVuaXQ+CiAgICAgICAgIDxleGlmOlBpeGVs"
    "WURpbWVuc2lvbj41OTA8L2V4aWY6UGl4ZWxZRGltZW5zaW9uPgogICAgICAgICA8ZXhpZjpQaXhlbFhEaW1lbnNp"
    "b24+ODU1PC9leGlmOlBpeGVsWERpbWVuc2lvbj4KICAgICAgICAgPGV4aWY6Q29sb3JTcGFjZT4xPC9leGlmOkNv"
    "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"
)
# a term another site explains better links there instead of to terms.html
MORE_LINKS = {"survey-days": BLITZ}

CSS = """
:root{--bg:#fbfbf9;--panel:#fff;--ink:#1d1d1b;--muted:#5f5e58;--line:#dcdbd3;--dot:42,120,214;
  --bar:#206dcb;--total:#d5e3f5;--share:#c2410c;--chip:#f0efe9;--on:#1d1d1b;--onink:#fff;
--warn:#8a4b00;--warnbg:#fdf0dc;--good:#1a7f37;
  --shadow:0 4px 16px rgba(0,0,0,.18)}
@media (prefers-color-scheme:dark){:root:not([data-theme="light"]){--bg:#1a1a19;--panel:#222220;
  --ink:#fff;--muted:#c3c2b7;--line:#3a3a37;--dot:57,135,229;--bar:#529aeb;--total:#2b3a4d;
--share:#fb923c;--chip:#2c2c2a;--on:#fff;
  --onink:#1a1a19;--warn:#ffc27a;--warnbg:#3a2a14;--good:#57d17a;
  --shadow:0 4px 16px rgba(0,0,0,.5)}}
:root[data-theme="dark"]{--bg:#1a1a19;--panel:#222220;--ink:#fff;--muted:#c3c2b7;--line:#3a3a37;
  --dot:57,135,229;--bar:#529aeb;--total:#2b3a4d;--share:#fb923c;--chip:#2c2c2a;--on:#fff;
--onink:#1a1a19;--warn:#ffc27a;
  --warnbg:#3a2a14;--good:#57d17a;--shadow:0 4px 16px rgba(0,0,0,.5)}
:focus-visible{outline:3px solid var(--bar);outline-offset:2px}
@media (prefers-reduced-motion:reduce){*,::before,::after{
  transition-duration:.01ms!important;animation-duration:.01ms!important;
  scroll-behavior:auto!important}}
.site-skip{position:absolute;left:8px;top:8px;z-index:100;transform:translateY(-200%);
padding:10px 14px;
  background:var(--panel);color:var(--ink);border:1px solid var(--line);border-radius:6px}
.site-skip:focus{transform:none}
.site-shell{grid-area:nav;min-width:0;display:flex;align-items:center;gap:0 16px;padding:0 16px;
  background:var(--panel);color:var(--ink);border-bottom:1px solid var(--line);
  font:14px/1.4 system-ui,-apple-system,"Segoe UI",sans-serif}
.site-brand{display:inline-flex;align-items:center;min-height:44px;font-weight:700;font-size:15px;
  color:var(--ink);text-decoration:none;white-space:nowrap}
.site-nav{position:relative;display:flex;flex:1 1 auto;min-width:0;gap:0 4px;
  overflow-x:auto;scrollbar-width:none}
.site-nav::-webkit-scrollbar{display:none}
.site-nav a{display:inline-flex;align-items:center;min-height:44px;padding:0 12px;
color:var(--muted);
  text-decoration:none;border-bottom:3px solid transparent;white-space:nowrap}
.site-nav a:hover{color:var(--ink);background:var(--chip)}
.site-nav a[aria-current="page"]{color:var(--ink);font-weight:650;border-bottom-color:var(--on)}
.site-nav .ext{margin-left:auto;font-size:.875em}
.infob{display:inline-flex;align-items:center;justify-content:center;flex:none;width:28px;
height:28px;padding:0;border:1px solid var(--line);border-radius:999px;background:var(--panel);
color:var(--ink);cursor:pointer}
.infob:hover{border-color:var(--ink)}
.infob svg{width:20px;height:20px;fill:none;stroke:currentColor;stroke-width:2.2;
stroke-linecap:round}
.site-mark{height:16px;width:auto;margin-right:6px;vertical-align:middle}
@media (max-width:480px){.site-nav .ext{display:none}}
.site-vh{position:absolute;width:1px;height:1px;overflow:hidden;clip:rect(0 0 0 0);
white-space:nowrap}
.embed .site-shell,.embed .site-skip{display:none}
@media (max-width:640px){.site-shell{padding:0 8px;gap:0 8px}.site-nav a{padding:0 9px}
.site-nav{--fade:linear-gradient(90deg,transparent,#000 16px,#000 calc(100% - 16px),transparent);
-webkit-mask-image:var(--fade);mask-image:var(--fade)}}
@media (max-width:480px){.site-bc{display:none}}
""".strip()

# Points the switcher at what is open. Reads the hash the pages already write: the map keeps
# record=, the photo pages keep id=; the selection (groups, taxa, dates) goes
# to the map and the photo space as written. One group (g= on Confused pairs, a lone picked
# groups= on Explore) travels between the two. Rewrites on hover, focus, touch and click
# because history.replaceState fires no event.
JS = """
(function(){var n=document.querySelector('.site-nav');if(!n)return;
function ctx(){var h=new URLSearchParams(location.hash.slice(1)),
gs=(h.get('groups')||'').split(',');
return{grp:h.get('g')||(gs.length===1&&/^[^-]/.test(gs[0])?gs[0]:''),rec:+(h.get('record')||h.get('id'))||0,
sel:location.hash.slice(1).split('&').filter(function(t){
return /^(by|from|to|months|groups|only|acc|taxa|area|park|bcpark|projects)=/.test(t);})};}
function h0(sel){return sel.some(function(t){return t.indexOf('groups=')===0;});}
function sync(){var c=ctx();n.querySelectorAll('a[data-view]').forEach(function(a){
var b=a.dataset.base,v=a.dataset.view,u=b;
if(a.hasAttribute('aria-current')&&v!=='explore')return;
if(v==='explore'){var p=[];if(c.rec)p.push('id='+c.rec);p=p.concat(c.sel);
if(c.grp&&!h0(c.sel))p.push('groups='+encodeURIComponent(c.grp));
if(p.length)u=b+'#'+p.join('&');}
else if(v==='group'&&c.grp)u=b+'#g='+encodeURIComponent(c.grp);
a.href=u;});}
['mouseover','focusin','touchstart',
'click'].forEach(function(e){n.addEventListener(e,sync,true);});
var cur=n.querySelector('[aria-current]');
if(cur)n.scrollLeft+=cur.getBoundingClientRect().left-n.getBoundingClientRect().left-
(n.clientWidth-cur.offsetWidth)/2;
addEventListener('hashchange',sync);sync();
if(n.hasAttribute('data-probe'))n.querySelectorAll('a[data-optional],a[data-fallback]').forEach(function(a){
fetch(a.dataset.base,{method:'HEAD'}).then(function(r){if(r.ok)return;
if(a.dataset.fallback){a.dataset.base=a.dataset.fallback;a.dataset.view='';
a.href=a.dataset.base;}else a.remove();
}).catch(function(){});});})();
""".strip()

# The toggletips (site_assets/explain.js) and the glossary go on every page nav draws.
_EXPLAIN = Path(__file__).parent / "site_assets"


def explain() -> str:
    """The toggletips' style, the glossary as JSON and the script, for the end of the header."""
    linked = {k: (d, u, MORE_LINKS.get(k, f"terms.html#{k}")) for k, (d, u) in GLOSSARY.items()}
    data = json.dumps(linked, separators=(",", ":")).replace("<", "\\u003c")
    return (
        f"<style>{(_EXPLAIN / 'explain.css').read_text().strip()}</style>\n"
        f'<script type="application/json" id="explain-data">{data}</script>\n'
        f"<script>{(_EXPLAIN / 'explain.js').read_text().strip()}</script>\n"
    )


_EXPLORE_OF = ("explore.html", "map.html", "embeddings.html", "tree.html", "search.html")
_SKIP = (
    "onclick=\"event.preventDefault();var m=document.getElementById('main-content')"
    "||document.querySelector('main');m.tabIndex=-1;m.focus()\""
)


def nav(
    current: str,
    available: set[str] | None = None,
    *,
    base: str = "",
    extra: str = "",
) -> str:
    """Skip link, brand and switcher with `current` marked. `available` lists the built pages.

    With `available=None` the page cannot know which optional pages exist, so the script drops
    the ones that answer 404. `base` prefixes the links of a page served from another folder.
    `extra` is html placed at the end of the header row (the split page's view switch and counts).
    """
    links = []
    here = EXPLORE if current in _EXPLORE_OF else current
    for page, label in PAGES:
        if available is not None and page not in available and page != here:
            continue
        href = base + page
        attrs = ' aria-current="page"' if page == here else ""
        if page == EXPLORE and available is not None and page not in available:
            href = base + "map.html"
        elif page == EXPLORE:
            attrs += f' data-view="explore" data-fallback="{escape(base)}map.html"'
        if page in OPTIONAL:
            attrs += ' data-optional data-view="group"'
        attrs += f' data-base="{escape(href)}"'
        links.append(f'<a href="{escape(href)}"{attrs}>{escape(label)}</a>')
    links.append(
        f'<a class="ext" href="{SITE[0]}" target="_blank" rel="noopener">'
        f'<img class="site-mark" src="{SITE_MARK}" alt="">{SITE[1]}\u00a0'
        '<span aria-hidden="true">\u2197</span>'
        '<span class="site-vh"> (opens in a new tab)</span></a>'
    )
    flags = " data-probe" if available is None else ""
    return (
        f'<a class="site-skip" href="#main-content" {_SKIP}>Skip to content</a>\n'
        f'<div class="site-shell"><a class="site-brand" href="{escape(base)}index.html">'
        'What to ID<span class="site-bc">\u00a0· BC</span></a>'
        f'<nav class="site-nav" aria-label="Views"{flags}>{"".join(links)}</nav>{extra}</div>\n'
        f"<script>{JS}</script>\n" + explain()
    )


# Identify is the whole app, so it swaps the view switcher for a wordmark and a Help menu that
# reaches the other pages. Confused pairs drops out when it answers 404, Explore shows only when
# it answers (the same HEAD check the switcher uses).
HELP_LINKS = (
    ("terms.html", "How it works", ""),
    ("confusion.html", "Confused pairs", " data-drop"),
    ("explore.html", "Explore", " data-show hidden"),
)
HELP_CSS = """
.appbar{max-width:1100px;margin:0 auto;padding:0 12px;display:flex;align-items:center;
  justify-content:space-between;gap:8px;min-height:44px;
  font:14px/1.4 system-ui,-apple-system,"Segoe UI",sans-serif}
.appbar .site-brand{color:var(--ink)}
.hm{position:relative}
.hm>button{display:inline-flex;align-items:center;gap:6px;min-height:44px;padding:0 10px;
  font:inherit;color:var(--ink);background:none;border:0;border-radius:6px;cursor:pointer}
.hm>button:hover,.hm>button[aria-expanded=true]{background:var(--chip)}
.hm svg{width:18px;height:18px;fill:none;stroke:currentColor;stroke-width:2;stroke-linecap:round}
.hm ul{position:absolute;right:0;top:100%;z-index:60;margin:0;padding:4px;list-style:none;
  min-width:11em;background:var(--panel);border:1px solid var(--line);border-radius:12px;
  box-shadow:var(--shadow)}
.hm li a{display:flex;align-items:center;min-height:44px;padding:0 12px;border-radius:6px;
  color:var(--ink);text-decoration:none;white-space:nowrap}
.hm li a:hover{background:var(--chip)}
.hm [hidden]{display:none!important}
.embed .appbar{display:none}
""".strip()
HELP_JS = """
(function(){var b=document.getElementById('hmbtn'),m=document.getElementById('hmenu');if(!b)return;
function set(o){m.hidden=!o;b.setAttribute('aria-expanded',String(o));}
b.onclick=function(){set(m.hidden);};
document.addEventListener('keydown',function(e){if(e.key==='Escape'&&!m.hidden){set(false);b.focus();}});
document.addEventListener('click',function(e){if(!m.hidden&&!b.parentNode.contains(e.target))set(false);});
m.addEventListener('focusout',function(e){if(e.relatedTarget&&!b.parentNode.contains(e.relatedTarget))set(false);});
m.querySelectorAll('a[data-drop],a[data-show]').forEach(function(a){
fetch(a.getAttribute('href'),{method:'HEAD'}).then(function(r){
if(r.ok)a.parentNode.hidden=false;else if(a.hasAttribute('data-drop'))a.parentNode.remove();
}).catch(function(){});});})();
""".strip()


def help_bar(base: str = "") -> str:
    """Skip link, wordmark and the Help menu, for the page that is the whole app (Identify)."""
    items = "".join(
        f"<li{' hidden' if 'hidden' in flags else ''}>"
        f'<a href="{escape(base + page)}"{flags.replace(" hidden", "")}>{label}</a></li>'
        for page, label, flags in HELP_LINKS
    )
    icon = (
        '<svg viewBox="0 0 24 24" aria-hidden="true"><circle cx="12" cy="12" r="9"/>'
        '<path d="M9.5 9.5a2.5 2.5 0 1 1 3.5 2.3c-.7.4-1 .9-1 1.7M12 17h.01"/></svg>'
    )
    return (
        f'<a class="site-skip" href="#main-content" {_SKIP}>Skip to content</a>\n'
        f'<div class="appbar"><a class="site-brand" href="{escape(base)}index.html">'
        'What to ID<span class="site-bc">\u00a0· BC</span></a>'
        f'<div class="hm"><button type="button" id="hmbtn" aria-expanded="false" '
        f'aria-controls="hmenu">{icon}Help</button>'
        f'<ul id="hmenu" aria-label="Help" hidden>{items}</ul></div></div>\n'
        f"<script>{HELP_JS}</script>\n" + explain()
    )
