"""A map of the day's pool: every record as a point, filtered by taxon group and observed date.

The page (map.html) loads MapLibre and deck.gl from a CDN and reads the points from pool.bin, a
column file next to it. The file holds record ids, positions, observed dates and groups, sorted
by id, and nothing about lists, so the map cannot tell which list a record sits on.

pool.bin layout, little-endian, n records, columns back to back:
    uint32 id[n] | uint16 lon[n] | uint16 lat[n] | uint16 obs[n] | uint16 up[n] | uint8 group[n]
lon and lat are quantized over the bounding box in the page's META; obs (observed) and up
(uploaded) count days from META.day0, with NO_DAY for a missing date; group indexes META.groups.
The page filters on either date: iNaturalist records are often uploaded days or months after
they were made, so observed is the default and uploaded is one click away.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import logging
from html import escape
from pathlib import Path

import numpy as np
import pandas as pd

from what_to_id.page import ARM_WORDS, group_name

BIN_NAME = "pool.bin"
MAP_NAME = "map.html"
NO_DAY = 0xFFFF
_Q = 0xFFFF
BYTES_PER_RECORD = 13
_COLS = ("id", "lat", "lon", "observed_on", "created_at", "iconic_taxon")


def encode_points(pool: pd.DataFrame) -> tuple[bytes, dict]:
    """Pack the pool into pool.bin bytes and the META the page needs to read them."""
    missing = [c for c in _COLS if c not in pool]
    if missing:
        raise ValueError(f"pool lacks columns {missing}")
    if pool.empty:
        raise ValueError("pool is empty; nothing to map")
    df = pool[list(_COLS)].sort_values("id")
    ids = df["id"].to_numpy(dtype=np.int64)
    if ids.min() < 0 or ids.max() > 0xFFFFFFFF:
        raise ValueError("record ids do not fit in uint32")
    lat = df["lat"].to_numpy(dtype=np.float64)
    lon = df["lon"].to_numpy(dtype=np.float64)
    if not (np.isfinite(lat).all() and np.isfinite(lon).all()):
        raise ValueError("pool has records without coordinates")
    bbox = [float(lon.min()), float(lat.min()), float(lon.max()), float(lat.max())]

    def quant(v: np.ndarray, lo: float, hi: float) -> np.ndarray:
        span = hi - lo or 1.0
        return np.rint((v - lo) / span * _Q).astype("<u2")

    obs = _dates(df["observed_on"])
    up = _dates(df["created_at"])
    day0 = min(d for d in (obs.min(), up.min()) if pd.notna(d)) if obs.notna().any() else None
    if day0 is None:
        raise ValueError("no record has an observed date")
    obs_off, up_off = (obs - day0).dt.days, (up - day0).dt.days
    last = int(max(obs_off.max(), up_off.max()))
    if last >= NO_DAY:
        raise ValueError("dates span more than 65,534 days")
    groups = sorted(df["iconic_taxon"].fillna("Unknown").astype(str).unique())
    gidx = pd.Categorical(df["iconic_taxon"].fillna("Unknown").astype(str), categories=groups)
    blob = b"".join(
        (
            ids.astype("<u4").tobytes(),
            quant(lon, bbox[0], bbox[2]).tobytes(),
            quant(lat, bbox[1], bbox[3]).tobytes(),
            obs_off.fillna(NO_DAY).to_numpy().astype("<u2").tobytes(),
            up_off.fillna(NO_DAY).to_numpy().astype("<u2").tobytes(),
            gidx.codes.astype("u1").tobytes(),
        )
    )
    meta = {
        "n": int(len(df)),
        "bbox": bbox,
        "day0": day0.strftime("%Y-%m-%d"),
        "days": last + 1,
        "groups": groups,
        "names": {g: group_name(g) for g in groups},
        "sha256": hashlib.sha256(blob).hexdigest(),
    }
    return blob, meta


def decode_points(blob: bytes, meta: dict) -> pd.DataFrame:
    """Read pool.bin back, as the page does; for tests and for a QGIS export."""
    n = int(meta["n"])
    if len(blob) != BYTES_PER_RECORD * n:
        raise ValueError(f"pool.bin holds {len(blob)} bytes, expected {BYTES_PER_RECORD * n}")
    ids = np.frombuffer(blob, "<u4", n, 0)
    qlon = np.frombuffer(blob, "<u2", n, 4 * n)
    qlat = np.frombuffer(blob, "<u2", n, 6 * n)
    obs = np.frombuffer(blob, "<u2", n, 8 * n)
    up = np.frombuffer(blob, "<u2", n, 10 * n)
    grp = np.frombuffer(blob, "u1", n, 12 * n)
    x0, y0, x1, y1 = meta["bbox"]
    day0 = pd.Timestamp(meta["day0"])

    def date(d: np.ndarray) -> pd.Series:
        return pd.Series(day0 + pd.to_timedelta(np.where(d == NO_DAY, 0, d), "D")).where(
            d != NO_DAY
        )

    return pd.DataFrame(
        {
            "id": ids.astype(np.int64),
            "lon": x0 + qlon / _Q * (x1 - x0),
            "lat": y0 + qlat / _Q * (y1 - y0),
            "observed_on": date(obs),
            "uploaded_on": date(up),
            "iconic_taxon": np.asarray(meta["groups"], dtype=object)[grp],
        }
    )


def _dates(col: pd.Series) -> pd.Series:
    """Calendar dates; created_at is UTC, observed_on is the observer's local date."""
    d = pd.to_datetime(col, errors="coerce", utc=True, format="mixed")
    return d.dt.tz_localize(None).dt.normalize()


def render_map(meta: dict, *, freeze: str | None, back: str = "index.html") -> str:
    """The map page. META goes inline; the points come from pool.bin at load."""
    when = f" on {escape(freeze)}" if freeze else ""
    title = "Records that need an ID in BC"
    page_meta = {**meta, "bin": f"{BIN_NAME}?v={meta['sha256'][:12]}"}
    return (
        '<!doctype html>\n<html lang="en">\n<head>\n<meta charset="utf-8">\n'
        '<meta name="viewport" content="width=device-width,initial-scale=1">\n'
        f"<title>{title}</title>\n"
        f'<link rel="stylesheet" href="{MAPLIBRE_CSS}">\n'
        f'<script src="{MAPLIBRE_JS}"></script>\n<script src="{DECK_JS}"></script>\n'
        f"<style>{MAP_CSS}</style>\n</head>\n<body>\n"
        '<header><div class="head">'
        f'<h1>{title}</h1><p class="sub">Each dot is one record that needed an ID and had a photo'
        f'{when}. Click a dot to open it in iNaturalist. <a href="{escape(back)}">Back</a></p>'
        "</div>"
        '<div class="ctl"><div id="groups" role="group" aria-label="Taxon groups"></div>'
        '<div class="time"><canvas id="hist" height="44" aria-hidden="true"></canvas>'
        '<div class="range"><input id="t0" type="range" min="0" step="1" aria-label="From">'
        '<input id="t1" type="range" min="0" step="1" aria-label="To"></div>'
        '<p class="stat"><span class="seg" role="group" aria-label="Date">'
        '<button type="button" id="byObs" aria-pressed="true">Observed</button>'
        '<button type="button" id="byUp" aria-pressed="false">Uploaded</button></span> '
        '<span id="span"></span> <b id="count">Loading</b></p></div></div>'
        "</header>\n"
        '<div id="map" role="application" aria-label="Map of records"></div>\n'
        '<p class="note">Records whose observer or taxon hides the exact place show at '
        "iNaturalist's public point, up to about 20 km from where they were made.</p>\n"
        f"<script>var META={json.dumps(page_meta, sort_keys=True)};{MAP_JS}</script>\n"
        "</body>\n</html>\n"
    )


def write_map(out_dir: Path | str, pool: pd.DataFrame, *, freeze: str | None = None) -> list[Path]:
    """Write map.html and pool.bin into the site folder."""
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    blob, meta = encode_points(pool)
    html = render_map(meta, freeze=freeze)
    low = html.lower()
    for w in ARM_WORDS:
        if w in low:
            raise ValueError(f"{MAP_NAME}: arm name {w!r} leaked into the map page")
    (out / BIN_NAME).write_bytes(blob)
    (out / MAP_NAME).write_text(html)
    return [out / MAP_NAME, out / BIN_NAME]


MAPLIBRE_JS = "https://unpkg.com/maplibre-gl@4.7.1/dist/maplibre-gl.js"
MAPLIBRE_CSS = "https://unpkg.com/maplibre-gl@4.7.1/dist/maplibre-gl.css"
DECK_JS = "https://unpkg.com/deck.gl@9.1.14/dist.min.js"
BASEMAPS = {
    "light": "https://basemaps.cartocdn.com/gl/positron-gl-style/style.json",
    "dark": "https://basemaps.cartocdn.com/gl/dark-matter-gl-style/style.json",
}

_LIGHT = (
    "--bg:#fbfbf9;--ink:#1d1d1b;--muted:#5f5e58;--line:#dcdbd3;--dot:42,120,214;"
    "--bar:#2a78d6;--chip:#f0efe9;--on:#1d1d1b;--onink:#fff"
)
_DARK = (
    "--bg:#1a1a19;--ink:#fff;--muted:#c3c2b7;--line:#3a3a37;--dot:57,135,229;"
    "--bar:#3987e5;--chip:#262624;--on:#fff;--onink:#1a1a19"
)
MAP_CSS = (
    f":root{{{_LIGHT}}}"
    f'@media (prefers-color-scheme:dark){{:root:not([data-theme="light"]){{{_DARK}}}}}'
    f':root[data-theme="dark"]{{{_DARK}}}'
    """
*{box-sizing:border-box}
html,body{margin:0;height:100%;background:var(--bg);color:var(--ink);
  font:15px/1.4 system-ui,-apple-system,"Segoe UI",sans-serif}
body{display:flex;flex-direction:column}
header{padding:12px 16px;border-bottom:1px solid var(--line);display:flex;flex-wrap:wrap;
  gap:8px 24px}
.head{flex:1 1 320px;min-width:0}
h1{font-size:18px;margin:0 0 2px}
.sub,.note,.stat{color:var(--muted);margin:0;font-size:13px}
.sub a{color:inherit}
.ctl{flex:2 1 480px;min-width:0;display:flex;flex-wrap:wrap;gap:8px 16px;align-items:flex-start}
#groups{display:flex;flex-wrap:wrap;gap:4px;flex:1 1 260px}
#groups button{border:1px solid var(--line);background:var(--chip);color:var(--ink);
  border-radius:12px;padding:3px 9px;font:inherit;font-size:12px;cursor:pointer;min-height:26px}
#groups button[aria-pressed="true"]{background:var(--on);color:var(--onink);border-color:var(--on)}
.time{flex:1 1 260px;min-width:0}
#hist{width:100%;height:44px;display:block}
.range{position:relative;height:22px}
.range input{position:absolute;inset:0;width:100%;margin:0;pointer-events:none;background:none;
  -webkit-appearance:none;appearance:none}
.range input::-webkit-slider-runnable-track{height:22px;background:none}
.range input::-webkit-slider-thumb{pointer-events:auto;-webkit-appearance:none;width:14px;
  height:18px;border-radius:4px;background:var(--ink);cursor:pointer}
.range input::-moz-range-thumb{pointer-events:auto;width:14px;height:18px;border-radius:4px;
  background:var(--ink);border:0;cursor:pointer}
.seg button{border:1px solid var(--line);background:var(--chip);color:var(--ink);font:inherit;
  font-size:12px;padding:2px 8px;cursor:pointer}
.seg button:first-child{border-radius:10px 0 0 10px}
.seg button:last-child{border-radius:0 10px 10px 0}
.seg button[aria-pressed="true"]{background:var(--on);color:var(--onink);border-color:var(--on)}
#map{flex:1;min-height:320px;position:relative}
.note{padding:6px 16px}
"""
)

MAP_JS = (
    f"var BASEMAPS={json.dumps(BASEMAPS, sort_keys=True)};"
    r"""
(function(){
var dark=matchMedia('(prefers-color-scheme: dark)').matches,
  css=getComputedStyle(document.documentElement),
  dot=css.getPropertyValue('--dot').split(',').map(Number),bar=css.getPropertyValue('--bar');
var DAY=864e5,d0=Date.parse(META.day0+'T00:00:00Z'),NO=65535,n=META.n,P=null;
function fmt(d){return new Date(d0+d*DAY).toISOString().slice(0,10);}
var t0=document.getElementById('t0'),t1=document.getElementById('t1');
t0.max=t1.max=META.days-1;t0.value=0;t1.value=META.days-1;
var on=META.groups.map(function(){return true;}),box=document.getElementById('groups');
META.groups.forEach(function(g,i){
  var b=document.createElement('button');b.type='button';b.textContent=META.names[g]||g;
  b.setAttribute('aria-pressed','true');
  b.onclick=function(){on[i]=!on[i];b.setAttribute('aria-pressed',String(on[i]));update();};
  box.appendChild(b);
});
var b=META.bbox,map=new maplibregl.Map({container:'map',
  style:dark?BASEMAPS.dark:BASEMAPS.light,bounds:[[b[0],b[1]],[b[2],b[3]]],
  fitBoundsOptions:{padding:20},attributionControl:{compact:true}});
map.addControl(new maplibregl.NavigationControl({showCompass:false}));
var overlay=new deck.MapboxOverlay({interleaved:false,layers:[]});map.addControl(overlay);
fetch(META.bin).then(function(r){
  if(!r.ok)throw new Error('HTTP '+r.status);return r.arrayBuffer();
}).then(function(buf){
  if(buf.byteLength!==13*n)throw new Error('unexpected size');
  var id=new Uint32Array(buf,0,n),qx=new Uint16Array(buf,4*n,n),qy=new Uint16Array(buf,6*n,n),
    obs=new Uint16Array(buf,8*n,n),up=new Uint16Array(buf,10*n,n),grp=new Uint8Array(buf,12*n,n),
    pos=new Float32Array(2*n),fo=new Float32Array(n),fu=new Float32Array(n),
    fg=new Float32Array(n),sx=(b[2]-b[0])/65535,sy=(b[3]-b[1])/65535;
  for(var i=0;i<n;i++){
    pos[2*i]=b[0]+qx[i]*sx;pos[2*i+1]=b[1]+qy[i]*sy;
    fo[i]=obs[i]===NO?-1:obs[i];fu[i]=up[i]===NO?-1:up[i];fg[i]=grp[i];
  }
  P={id:id,obs:obs,up:up,grp:grp,pos:pos,fo:fo,fu:fu,fg:fg};update();
}).catch(function(e){
  document.getElementById('count').textContent='Could not load the points ('+e.message+')';
});
var hist=document.getElementById('hist');
function draw(weeks,lo,hi){
  var w=hist.clientWidth,h=44,r=devicePixelRatio||1,c=hist.getContext('2d');
  hist.width=w*r;hist.height=h*r;c.scale(r,r);
  var m=Math.max.apply(null,weeks)||1,bw=w/weeks.length,a=lo/7|0,z=hi/7|0;
  c.fillStyle=bar;
  for(var k=0;k<weeks.length;k++){
    var y=weeks[k]/m*(h-2);c.globalAlpha=(k>=a&&k<=z)?1:.3;
    c.fillRect(k*bw,h-y,Math.max(bw-1,1),y);
  }
}
function tip(o){
  if(!P||o.index<0)return null;
  var i=o.index,g=META.groups[P.grp[i]];
  function d(v){return v===NO?'unknown':fmt(v);}
  return {text:(META.names[g]||g)+'\nObserved '+d(P.obs[i])+'\nUploaded '+d(P.up[i])+
    '\nRecord '+P.id[i]};
}
function open(o){
  if(P&&o.index>=0)window.open('https://www.inaturalist.org/observations/'+P.id[o.index],
    '_blank','noopener');
}
function update(){
  var lo=Math.min(+t0.value,+t1.value),hi=Math.max(+t0.value,+t1.value);
  document.getElementById('span').textContent=fmt(lo)+' to '+fmt(hi)+':';
  if(!P)return;
  var day=byUp?P.up:P.obs,weeks=new Array(Math.ceil(META.days/7)).fill(0),shown=0,cats=[];
  for(var i=0;i<n;i++){
    if(!on[P.grp[i]]||day[i]===NO)continue;
    weeks[day[i]/7|0]++;if(day[i]>=lo&&day[i]<=hi)shown++;
  }
  draw(weeks,lo,hi);
  document.getElementById('count').textContent=shown.toLocaleString('en-CA')+' records';
  on.forEach(function(v,i){if(v)cats.push(i);});
  overlay.setProps({getTooltip:tip,onClick:open,layers:[new deck.ScatterplotLayer({id:'pts',
    data:{length:n,attributes:{getPosition:{value:P.pos,size:2},
      getFilterValue:{value:byUp?P.fu:P.fo,size:1},getFilterCategory:{value:P.fg,size:1}}},
    getFillColor:[dot[0],dot[1],dot[2],110],radiusUnits:'pixels',getRadius:1.5,
    radiusMinPixels:1,radiusMaxPixels:6,stroked:false,pickable:true,
    extensions:[new deck.DataFilterExtension({filterSize:1,categorySize:1})],
    filterRange:[lo,hi],filterCategories:cats.length?cats:[-1]})]});
}
var byUp=false,bo=document.getElementById('byObs'),bu=document.getElementById('byUp');
function by(v){byUp=v;bo.setAttribute('aria-pressed',String(!v));
  bu.setAttribute('aria-pressed',String(v));update();}
bo.onclick=function(){by(false);};bu.onclick=function(){by(true);};
[t0,t1].forEach(function(el){el.addEventListener('input',update);});
addEventListener('resize',update);
update();
})();
"""
)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Write map.html and pool.bin from a pool parquet.")
    ap.add_argument("--pool", required=True, type=Path)
    ap.add_argument("--out", required=True, type=Path, help="site folder")
    ap.add_argument("--freeze", default=None, help="date the pool stands for, YYYY-MM-DD")
    a = ap.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    pool = pd.read_parquet(a.pool)
    for path in write_map(a.out, pool, freeze=a.freeze):
        logging.getLogger("what_to_id").info("wrote %s (%d bytes)", path, path.stat().st_size)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
