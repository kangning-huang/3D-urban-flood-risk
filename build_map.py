"""Build static HTML map using geemap and export via to_html().

This script is run by GitHub Actions (or locally) to generate index.html.
Earth Engine tile URLs expire after ~24 hours, so the Action is scheduled
to run daily to keep the map live.

Usage:
    python build_map.py          # writes index.html
"""

import json
import os
import sys
import traceback

# Must set USE_FOLIUM before importing geemap so that __init__.py loads
# foliumap directly, avoiding a namespace collision where geemap.geemap's
# `basemaps = Box(...)` shadows the geemap.basemaps module.
os.environ["USE_FOLIUM"] = "1"

import ee
import geemap
from folium import MacroElement
from jinja2 import Template

# ---------------------------------------------------------------------------
# Initialize Earth Engine
# ---------------------------------------------------------------------------
# In CI the service account credentials are written to a JSON file whose
# path is stored in GOOGLE_APPLICATION_CREDENTIALS.  Locally, the default
# credentials from `earthengine authenticate` are used.
EE_URL = "https://earthengine-highvolume.googleapis.com"
credentials_path = os.environ.get("GOOGLE_APPLICATION_CREDENTIALS")

try:
    if credentials_path and os.path.isfile(credentials_path):
        # CI / service-account path – read project from key file
        with open(credentials_path) as f:
            key_data = json.load(f)
        project = os.environ.get("GCP_PROJECT") or key_data.get("project_id")
        print(f"Initializing EE with project={project}")
        credentials = ee.ServiceAccountCredentials(None, credentials_path)
        ee.Initialize(credentials, project=project, opt_url=EE_URL)
    else:
        # Local development – use default credentials or prompt login
        try:
            ee.Initialize(opt_url=EE_URL)
        except Exception:
            ee.Authenticate()
            ee.Initialize(opt_url=EE_URL)
    print("Earth Engine initialized successfully")
except Exception as exc:
    print(f"ERROR initializing Earth Engine: {exc}", file=sys.stderr)
    traceback.print_exc()
    sys.exit(1)

# ---------------------------------------------------------------------------
# Load datasets
# ---------------------------------------------------------------------------
FLOOD_RISK_ID = (
    "users/Jiayong_Liang/Research_projects/FloodRiskViewGlobal_Jan2026_bh-JRC"
)
flood_risk = ee.Image(FLOOD_RISK_ID)

gdp_adm2 = ee.Image(
    "projects/sat-io/open-datasets/GRIDDED_HDI_GDP/adm2_gdp_perCapita_1990_2022"
)
pop_2020 = ee.Image("JRC/GHSL/P2023A/GHS_POP/2020")
total_gdp = gdp_adm2.select("PPP_2022").multiply(pop_2020)

flood_risk_sub = flood_risk.select(
    ["exDmg", "exDmg_pros", "exInunD", "exInunD_pros"]
)
flood_risk_gdp = total_gdp.multiply(flood_risk_sub)

# ---------------------------------------------------------------------------
# Visualization parameters
# ---------------------------------------------------------------------------
SINGLE_VIS = {
    "exDmg": {
        "min": 0, "max": 0.05,
        "palette": ["ffffff", "06bee1", "1768ac", "2541b2", "03256c"],
    },
    "exDmg_pros": {
        "min": 0, "max": 0.05,
        "palette": ["ffffff", "06bee1", "1768ac", "2541b2", "03256c"],
    },
    "exInunD": {
        "min": 0, "max": 0.1,
        "palette": ["ffffff", "c7e9b4", "7fcdbb", "41b6c4", "1d91c0", "225ea8", "0c2c84"],
    },
    "exInunD_pros": {
        "min": 0, "max": 0.1,
        "palette": ["ffffff", "c7e9b4", "7fcdbb", "41b6c4", "1d91c0", "225ea8", "0c2c84"],
    },
    "height": {
        "min": 0, "max": 50,
        "palette": ["f7fcb9", "d9f0a3", "addd8e", "78c679", "41ab5d", "238443", "005a32"],
    },
    "flopros_model": {
        "min": 0, "max": 1000,
        "palette": ["fee5d9", "fcae91", "fb6a4a", "de2d26", "a50f15"],
    },
}

GDP_PALETTE = [
    "001219", "005f73", "0a9396", "94d2bd", "e9d8a6",
    "ee9b00", "ca6702", "bb3e03", "ae2012", "9b2226",
]

BAND_LABELS = {
    "exDmg": "FD-AED (Flood Damage)",
    "exDmg_pros": "FD-AED-P (Flood Damage w/ Protection)",
    "exInunD": "IR-AED (Inundation Depth)",
    "exInunD_pros": "IR-AED-P (Inundation Depth w/ Protection)",
    "height": "Building Height",
    "flopros_model": "FLOPROS Protection Standard",
}

GDP_LABELS = {
    "exDmg": "GDP × FD-AED",
    "exDmg_pros": "GDP × FD-AED-P",
    "exInunD": "GDP × IR-AED",
    "exInunD_pros": "GDP × IR-AED-P",
}

# ---------------------------------------------------------------------------
# RGB composite presets
# ---------------------------------------------------------------------------
RGB_PRESETS = [
    {
        "name": "RGB: InunD / Dmg-P / Dmg (raw)",
        "image": flood_risk,
        "bands": ["exInunD", "exDmg_pros", "exDmg"],
        "min": 0.01, "max": 0.1,
    },
    {
        "name": "RGB: InunD / Dmg-P / Dmg (GDP-weighted)",
        "image": flood_risk_gdp,
        "bands": ["exInunD", "exDmg_pros", "exDmg"],
        "min": 100, "max": 10000,
    },
]

# ---------------------------------------------------------------------------
# Generate per-band grayscale tiles for RGB composite widget
# ---------------------------------------------------------------------------
GRAYSCALE_BANDS = {
    "exDmg":        {"min": 0, "max": 0.1,  "label": "FD-AED (Flood Damage)"},
    "exDmg_pros":   {"min": 0, "max": 0.1,  "label": "FD-AED-P (w/ Protection)"},
    "exInunD":      {"min": 0, "max": 0.2,  "label": "IR-AED (Inundation Depth)"},
    "exInunD_pros": {"min": 0, "max": 0.2,  "label": "IR-AED-P (w/ Protection)"},
    "height":       {"min": 0, "max": 100,  "label": "Building Height (m)"},
    "flopros_model":{"min": 0, "max": 1000, "label": "FLOPROS Model"},
}

print("Generating per-band tile URLs for RGB widget...")
band_tiles = {}
for band_name, info in GRAYSCALE_BANDS.items():
    try:
        map_id = flood_risk.select(band_name).getMapId({
            "min": info["min"], "max": info["max"],
            "palette": ["000000", "ffffff"],
        })
        band_tiles[band_name] = {
            "url": map_id["tile_fetcher"].url_format,
            "min": info["min"], "max": info["max"],
            "label": info["label"],
        }
        print(f"  + {band_name}")
    except Exception as e:
        print(f"  x {band_name}: {e}")
print(f"Generated tile URLs for {len(band_tiles)} bands")

# ---------------------------------------------------------------------------
# RGB Widget Template
# ---------------------------------------------------------------------------
RGB_WIDGET_TEMPLATE = Template("""
{% macro header(this, kwargs) %}
<style>
.rgb-widget{background:#fff;border-radius:6px;box-shadow:0 1px 5px rgba(0,0,0,.4);
  font-family:'Helvetica Neue',Arial,sans-serif;font-size:12px;min-width:210px;
  overflow:hidden;pointer-events:auto}
.rgb-hdr{background:#f8f8f8;padding:7px 10px;cursor:pointer;font-weight:600;
  display:flex;justify-content:space-between;align-items:center;
  border-bottom:1px solid #e0e0e0;user-select:none}
.rgb-hdr:hover{background:#eee}
.rgb-body{padding:8px 10px}
.rgb-ch{display:flex;align-items:center;margin-bottom:5px;gap:5px}
.rgb-ch b{width:14px;text-align:center;font-size:13px}
.rgb-ch select{flex:1;padding:3px 4px;border:1px solid #ccc;border-radius:3px;
  font-size:11px;background:#fff;cursor:pointer}
.rgb-rng{display:flex;align-items:center;gap:4px;margin:7px 0 5px}
.rgb-rng label{font-size:11px;color:#555}
.rgb-rng input{width:58px;padding:2px 4px;border:1px solid #ccc;border-radius:3px;
  font-size:11px;text-align:center}
.rgb-op{display:flex;align-items:center;gap:5px;margin:5px 0}
.rgb-op label{font-size:11px;color:#555}
.rgb-op input[type=range]{flex:1}
.rgb-op span{font-size:11px;width:28px;text-align:right}
.rgb-show{margin-bottom:6px}
.rgb-show label{font-size:11px;cursor:pointer}
.rgb-btn{background:#4285f4;color:#fff;border:none;padding:5px 0;border-radius:3px;
  cursor:pointer;font-size:12px;font-weight:500;width:100%;margin-top:4px}
.rgb-btn:hover{background:#3367d6}
</style>
{% endmacro %}

{% macro script(this, kwargs) %}
(function(){
var map = {{ this._parent.get_name() }};
var BD = {{ this.band_data }};
var bands = Object.keys(BD);

/* ---- Canvas-based RGB composite tile layer ---- */
var RGBLayer = L.GridLayer.extend({
  initialize: function(o){
    this._r=o.rBand; this._g=o.gBand; this._b=o.bBand;
    this._dMin=o.displayMin; this._dMax=o.displayMax;
    L.GridLayer.prototype.initialize.call(this,o);
  },
  setParams: function(r,g,b,mn,mx){
    this._r=r;this._g=g;this._b=b;this._dMin=mn;this._dMax=mx;this.redraw();
  },
  createTile: function(coords,done){
    var cv=document.createElement('canvas'), sz=this.getTileSize();
    cv.width=sz.x; cv.height=sz.y;
    var self=this, ch=[this._r,this._g,this._b], loaded=0, pix=[null,null,null];
    ch.forEach(function(band,i){
      var img=new Image(); img.crossOrigin='anonymous';
      img.onload=function(){
        var tc=document.createElement('canvas'); tc.width=sz.x; tc.height=sz.y;
        var tx=tc.getContext('2d'); tx.drawImage(img,0,0,sz.x,sz.y);
        pix[i]=tx.getImageData(0,0,sz.x,sz.y).data;
        if(++loaded===3) self._blend(cv,pix,ch,sz,done);
      };
      img.onerror=function(){
        pix[i]=new Uint8ClampedArray(sz.x*sz.y*4);
        if(++loaded===3) self._blend(cv,pix,ch,sz,done);
      };
      img.src=BD[band].url.replace('{z}',coords.z).replace('{x}',coords.x).replace('{y}',coords.y);
    });
    return cv;
  },
  _blend: function(cv,pix,ch,sz,done){
    var ctx=cv.getContext('2d'), out=ctx.createImageData(sz.x,sz.y), d=out.data;
    var dMin=this._dMin, dMax=this._dMax, dR=dMax-dMin;
    for(var i=0;i<d.length;i+=4){
      var a=0;
      for(var c=0;c<3;c++){
        var raw=pix[c][i], alpha=pix[c][i+3];
        if(alpha>0) a=255;
        var bi=BD[ch[c]], val=(raw/255)*(bi.max-bi.min)+bi.min;
        d[i+c]=Math.max(0,Math.min(255,((val-dMin)/dR)*255));
      }
      d[i+3]=a;
    }
    ctx.putImageData(out,0,0); done(null,cv);
  }
});

var rgbLayer = new RGBLayer({
  rBand:'exInunD', gBand:'exDmg_pros', bBand:'exDmg',
  displayMin:0.01, displayMax:0.1, opacity:0.7
}).addTo(map);

/* ---- Control panel ---- */
function mkSel(id,def){
  var h='<select id="'+id+'">';
  bands.forEach(function(b){h+='<option value="'+b+'"'+(b===def?' selected':'')+'>'+BD[b].label+'</option>';});
  return h+'</select>';
}

var RGBCtrl = L.Control.extend({
  options:{position:'topright'},
  onAdd: function(){
    var d=L.DomUtil.create('div','rgb-widget');
    L.DomEvent.disableClickPropagation(d);
    L.DomEvent.disableScrollPropagation(d);
    d.innerHTML=
      '<div class="rgb-hdr" id="rgb-hdr"><span>RGB Composite</span><span id="rgb-arr">&#9660;</span></div>'+
      '<div class="rgb-body" id="rgb-body">'+
        '<div class="rgb-show"><label><input type="checkbox" id="rgb-show" checked> Show layer</label></div>'+
        '<div class="rgb-ch"><b style="color:#e74c3c">R</b>'+mkSel('rgb-r','exInunD')+'</div>'+
        '<div class="rgb-ch"><b style="color:#27ae60">G</b>'+mkSel('rgb-g','exDmg_pros')+'</div>'+
        '<div class="rgb-ch"><b style="color:#2980b9">B</b>'+mkSel('rgb-b','exDmg')+'</div>'+
        '<div class="rgb-rng"><label>Min</label><input type="number" id="rgb-mn" value="0.01" step="0.001">'+
          '<span>&ndash;</span><label>Max</label><input type="number" id="rgb-mx" value="0.1" step="0.001"></div>'+
        '<div class="rgb-op"><label>Opacity</label>'+
          '<input type="range" id="rgb-op" min="0" max="1" step="0.05" value="0.7">'+
          '<span id="rgb-opv">0.70</span></div>'+
        '<button class="rgb-btn" id="rgb-go">Apply</button>'+
      '</div>';
    return d;
  }
});
new RGBCtrl().addTo(map);

/* ---- Events ---- */
document.getElementById('rgb-hdr').onclick=function(){
  var b=document.getElementById('rgb-body'), a=document.getElementById('rgb-arr');
  if(b.style.display==='none'){b.style.display='';a.innerHTML='&#9660;';}
  else{b.style.display='none';a.innerHTML='&#9654;';}
};
document.getElementById('rgb-show').onchange=function(){
  this.checked?map.addLayer(rgbLayer):map.removeLayer(rgbLayer);
};
document.getElementById('rgb-op').oninput=function(){
  document.getElementById('rgb-opv').textContent=parseFloat(this.value).toFixed(2);
};
document.getElementById('rgb-go').onclick=function(){
  rgbLayer.setParams(
    document.getElementById('rgb-r').value,
    document.getElementById('rgb-g').value,
    document.getElementById('rgb-b').value,
    parseFloat(document.getElementById('rgb-mn').value),
    parseFloat(document.getElementById('rgb-mx').value)
  );
  rgbLayer.setOpacity(parseFloat(document.getElementById('rgb-op').value));
};
})();
{% endmacro %}
""")

# ---------------------------------------------------------------------------
# Build the map
# ---------------------------------------------------------------------------
m = geemap.Map()
m.set_center(119.38, 31.12, 8)
m.add_basemap("OpenTopoMap")

# --- Single-band layers (initially hidden — user can toggle via layer control)
for band, vis in SINGLE_VIS.items():
    m.addLayer(
        flood_risk.select(band),
        {**vis, "opacity": 0.5},
        BAND_LABELS[band],
        shown=False,
    )

# --- GDP-weighted layers
gdp_bands = ["exDmg", "exDmg_pros", "exInunD", "exInunD_pros"]
for band in gdp_bands:
    m.addLayer(
        flood_risk_gdp.select(band),
        {"min": 100, "max": 10000, "palette": GDP_PALETTE, "opacity": 0.4},
        GDP_LABELS[band],
        shown=False,
    )

m.add_layer_control()

# --- RGB Composite Widget (interactive band selector + Canvas compositor) ---
rgb_widget = MacroElement()
rgb_widget._name = "RGBWidget"
rgb_widget.band_data = json.dumps(band_tiles)
rgb_widget._template = RGB_WIDGET_TEMPLATE
m.add_child(rgb_widget)

# ---------------------------------------------------------------------------
# Export
# ---------------------------------------------------------------------------
m.to_html("index.html", title="Global Flood Risk Viewer")
print("✓ Wrote index.html")
