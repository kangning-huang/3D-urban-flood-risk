"""Build static HTML map using geemap and export via to_html().

This script is run by GitHub Actions (or locally) to generate index.html.
Earth Engine tile URLs expire after ~24 hours, so the Action is scheduled
to run daily to keep the map live.

Usage:
    python build_map.py          # writes index.html
"""

import os

import ee
import geemap.foliumap as geemap

# ---------------------------------------------------------------------------
# Initialize Earth Engine
# ---------------------------------------------------------------------------
# In CI the service account credentials are written to a JSON file whose
# path is stored in GOOGLE_APPLICATION_CREDENTIALS.  Locally, the default
# credentials from `earthengine authenticate` are used.
EE_URL = "https://earthengine-highvolume.googleapis.com"
credentials_path = os.environ.get("GOOGLE_APPLICATION_CREDENTIALS")

if credentials_path and os.path.isfile(credentials_path):
    # CI / service-account path
    credentials = ee.ServiceAccountCredentials(None, credentials_path)
    ee.Initialize(credentials, opt_url=EE_URL)
else:
    # Local development – use default credentials or prompt login
    try:
        ee.Initialize(opt_url=EE_URL)
    except Exception:
        ee.Authenticate()
        ee.Initialize(opt_url=EE_URL)

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

# --- RGB composite presets (default one shown)
for i, preset in enumerate(RGB_PRESETS):
    m.addLayer(
        preset["image"],
        {
            "bands": preset["bands"],
            "min": preset["min"],
            "max": preset["max"],
        },
        preset["name"],
        shown=(i == 0),  # show first preset by default
    )

m.add_layer_control()

# ---------------------------------------------------------------------------
# Export
# ---------------------------------------------------------------------------
m.to_html("index.html", title="Global Flood Risk Viewer")
print("✓ Wrote index.html")
