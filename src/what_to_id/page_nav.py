"""Site header and view switcher shared by every published page. Stdlib only.

scripts/atlas_page.sh runs on a bare python3, so this must not import numpy, pandas or page_map.
`CSS` holds the colour tokens and the shell rules; `nav` returns the skip link, the header and the
script that points the switcher at what the viewer has open.
"""

from __future__ import annotations

from html import escape

# (file, label), one tab per job: Identify (levels.html, records at three levels), Explore and
# Look-alikes (confusion.html), with the study last. Explore is explore.html, the map, the photo
# space and the tree side by side; the pages map.html, embeddings.html, tree.html and search.html
# keep their URLs and mark Explore as current, as Explore's panes and its search box hold them.
# Without explore.html (a site built without the photo space) the Explore tab falls back to the
# map. Levels and look-alikes exist only when the atlas manifest lists their tables. The brand
# links to index.html, a copy of the landing page.
PAGES = (
    ("levels.html", "Identify"),
    ("explore.html", "Explore"),
    ("confusion.html", "Look-alikes"),
    ("study.html", "Study"),
)
OPTIONAL = {"levels.html", "confusion.html"}
EXPLORE = "explore.html"
BLITZ = "https://pollocklab.github.io/where-to-blitz/"

CSS = """
:root{--bg:#fbfbf9;--panel:#fff;--ink:#1d1d1b;--muted:#5f5e58;--line:#dcdbd3;--dot:42,120,214;
  --bar:#2a78d6;--total:#d5e3f5;--share:#c2410c;--chip:#f0efe9;--on:#1d1d1b;--onink:#fff;
--warn:#8a4b00;--warnbg:#fdf0dc;
  --shadow:0 4px 16px rgba(0,0,0,.18)}
@media (prefers-color-scheme:dark){:root:not([data-theme="light"]){--bg:#1a1a19;--panel:#222220;
  --ink:#fff;--muted:#c3c2b7;--line:#3a3a37;--dot:57,135,229;--bar:#3987e5;--total:#2b3a4d;
--share:#fb923c;--chip:#2c2c2a;--on:#fff;
  --onink:#1a1a19;--warn:#ffc27a;--warnbg:#3a2a14;--shadow:0 4px 16px rgba(0,0,0,.5)}}
:root[data-theme="dark"]{--bg:#1a1a19;--panel:#222220;--ink:#fff;--muted:#c3c2b7;--line:#3a3a37;
  --dot:57,135,229;--bar:#3987e5;--total:#2b3a4d;--share:#fb923c;--chip:#2c2c2a;--on:#fff;
--onink:#1a1a19;--warn:#ffc27a;
  --warnbg:#3a2a14;--shadow:0 4px 16px rgba(0,0,0,.5)}
:focus-visible{outline:3px solid var(--bar);outline-offset:2px}
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
.site-vh{position:absolute;width:1px;height:1px;overflow:hidden;clip:rect(0 0 0 0);
white-space:nowrap}
.embed .site-shell,.embed .site-skip{display:none}
@media (max-width:640px){.site-shell{padding:0 8px;gap:0 8px}.site-nav a{padding:0 9px}
.site-nav{--fade:linear-gradient(90deg,transparent,#000 16px,#000 calc(100% - 16px),transparent);
-webkit-mask-image:var(--fade);mask-image:var(--fade)}}
@media (max-width:480px){.site-bc{display:none}}
""".strip()

# Points the switcher at what is open. Reads the hash the pages already write: the map keeps
# record= and at=zoom/lat/lon, the photo pages keep id=; the selection (groups, taxa, dates) goes
# to the map and the photo space as written. One group (g= on Identify and Look-alikes, a lone
# picked groups= on Explore) travels between the three. Rewrites on hover, focus, touch and click
# because history.replaceState fires no event.
JS = """
(function(){var n=document.querySelector('.site-nav');if(!n)return;
function ctx(){var h=new URLSearchParams(location.hash.slice(1)),
at=(h.get('at')||'').split('/').map(Number);
var ok=at.length===3&&at.every(isFinite),gs=(h.get('groups')||'').split(',');
return{grp:h.get('g')||(gs.length===1&&/^[^-]/.test(gs[0])?gs[0]:''),rec:+(h.get('record')||h.get('id'))||0,
lat:ok?at[1]:null,lon:ok?at[2]:null,sel:location.hash.slice(1).split('&').filter(function(t){
return /^(by|from|to|months|groups|only|acc|taxa|area|park|bcpark|projects)=/.test(t);})};}
function h0(sel){return sel.some(function(t){return t.indexOf('groups=')===0;});}
function sync(){var c=ctx();n.querySelectorAll('a[data-view]').forEach(function(a){
var b=a.dataset.base,v=a.dataset.view,u=b;
if(a.hasAttribute('aria-current')&&v!=='explore')return;
if(v==='explore'){var p=[];if(c.rec)p.push('id='+c.rec);p=p.concat(c.sel);
if(c.grp&&!h0(c.sel))p.push('groups='+encodeURIComponent(c.grp));
if(p.length)u=b+'#'+p.join('&');}
else if(v==='group'&&c.grp)u=b+'#g='+encodeURIComponent(c.grp);
else if(v==='blitz'&&c.lat!==null)u=b+'?at='+c.lat.toFixed(3)+','+c.lon.toFixed(3);
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

_EXPLORE_OF = ("map.html", "embeddings.html", "tree.html", "search.html")
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
        f'<a class="ext" href="{BLITZ}" target="_blank" rel="noopener" data-view="blitz" '
        f'data-base="{BLITZ}">Where to Blitz\u00a0<span aria-hidden="true">\u2197</span>'
        '<span class="site-vh"> (opens in a new tab)</span></a>'
    )
    flags = " data-probe" if available is None else ""
    return (
        f'<a class="site-skip" href="#main-content" {_SKIP}>Skip to content</a>\n'
        f'<div class="site-shell"><a class="site-brand" href="{escape(base)}index.html">'
        'What to ID<span class="site-bc"> · BC</span></a>'
        f'<nav class="site-nav" aria-label="Views"{flags}>{"".join(links)}</nav>{extra}</div>\n'
        f"<script>{JS}</script>\n"
    )
