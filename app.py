import ee
import geemap.foliumap as geemap
import streamlit as st

st.set_page_config(layout="wide", page_title="Global Flood Risk Viewer")

st.title("Global Flood Risk Viewer")
st.caption("Interactive visualization of global flood risk layers from GEE")

# --- Authenticate & initialize GEE ---
@st.cache_resource
def init_ee():
    try:
        ee.Initialize(opt_url="https://earthengine-highvolume.googleapis.com")
    except Exception:
        ee.Authenticate()
        ee.Initialize(opt_url="https://earthengine-highvolume.googleapis.com")

init_ee()

# --- Load datasets ---
FLOOD_RISK_ID = "users/Jiayong_Liang/Research_projects/FloodRiskViewGlobal_Jan2026_bh-JRC"
flood_risk = ee.Image(FLOOD_RISK_ID)

gdp_adm2 = ee.Image(
    "projects/sat-io/open-datasets/GRIDDED_HDI_GDP/adm2_gdp_perCapita_1990_2022"
)
pop_2020 = ee.Image("JRC/GHSL/P2023A/GHS_POP/2020")
total_gdp_2020 = gdp_adm2.select("PPP_2022").multiply(pop_2020)

flood_risk_sub = flood_risk.select(["exDmg", "exDmg_pros", "exInunD", "exInunD_pros"])
flood_risk_gdp = total_gdp_2020.multiply(flood_risk_sub)

# --- Band metadata ---
BAND_INFO = {
    "exDmg": "FD-AED (Flood Damage - Annual Expected Damage)",
    "exDmg_pros": "FD-AED-P (Flood Damage - AED with Protection)",
    "exInunD": "IR-AED (Inundation Risk - Annual Expected Depth)",
    "exInunD_pros": "IR-AED-P (Inundation Risk - AED with Protection)",
    "height": "Building Height",
    "flopros_model": "FLOPROS Protection Standard",
}

SINGLE_LAYER_PALETTES = {
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

# --- Sidebar controls ---
st.sidebar.header("Layer Controls")

# Individual layers
st.sidebar.subheader("Single-Band Layers")
selected_bands = []
for band, label in BAND_INFO.items():
    if st.sidebar.checkbox(label, value=False, key=f"cb_{band}"):
        selected_bands.append(band)

# GDP-weighted layer
st.sidebar.subheader("GDP-Weighted Layers")
gdp_bands = ["exDmg", "exDmg_pros", "exInunD", "exInunD_pros"]
gdp_band_labels = {b: f"GDP × {BAND_INFO[b]}" for b in gdp_bands}
selected_gdp = []
for band in gdp_bands:
    if st.sidebar.checkbox(gdp_band_labels[band], value=False, key=f"gdp_{band}"):
        selected_gdp.append(band)

# RGB composite
st.sidebar.subheader("RGB Composite")
enable_rgb = st.sidebar.checkbox("Enable RGB Composite", value=True)

all_bands = list(BAND_INFO.keys())
if enable_rgb:
    st.sidebar.markdown("Assign a band to each color channel:")
    rgb_source = st.sidebar.radio(
        "Composite source",
        ["Flood Risk (raw)", "GDP-weighted Flood Risk"],
        index=0,
    )
    red_band = st.sidebar.selectbox("Red channel", all_bands if rgb_source == "Flood Risk (raw)" else gdp_bands, index=all_bands.index("exInunD") if rgb_source == "Flood Risk (raw)" else 0)
    green_band = st.sidebar.selectbox("Green channel", all_bands if rgb_source == "Flood Risk (raw)" else gdp_bands, index=all_bands.index("exDmg_pros") if rgb_source == "Flood Risk (raw)" else 1)
    blue_band = st.sidebar.selectbox("Blue channel", all_bands if rgb_source == "Flood Risk (raw)" else gdp_bands, index=all_bands.index("exDmg") if rgb_source == "Flood Risk (raw)" else 0)

    rgb_min = st.sidebar.number_input("RGB min", value=0.0, step=0.001, format="%.4f")
    rgb_max = st.sidebar.number_input("RGB max", value=0.05, step=0.001, format="%.4f")
    rgb_opacity = st.sidebar.slider("RGB opacity", 0.0, 1.0, 1.0, 0.05)

# Map opacity for single layers
layer_opacity = st.sidebar.slider("Single-layer opacity", 0.0, 1.0, 0.5, 0.05)

# --- Build map ---
m = geemap.Map()
m.set_center(119.38, 31.12, 8)
m.add_basemap("Esri.WorldTopoMap")

# Add single-band layers
for band in selected_bands:
    vis = SINGLE_LAYER_PALETTES.get(band, {"min": 0, "max": 1, "palette": ["ffffff", "000000"]})
    m.addLayer(
        flood_risk.select(band),
        {"min": vis["min"], "max": vis["max"], "palette": vis["palette"], "opacity": layer_opacity},
        BAND_INFO[band],
    )

# Add GDP-weighted layers
for band in selected_gdp:
    m.addLayer(
        flood_risk_gdp.select(band),
        {"min": 100, "max": 10000, "palette": GDP_PALETTE, "opacity": 0.4},
        gdp_band_labels[band],
    )

# Add RGB composite
if enable_rgb:
    src_img = flood_risk if rgb_source == "Flood Risk (raw)" else flood_risk_gdp
    rgb_vis = {
        "bands": [red_band, green_band, blue_band],
        "min": rgb_min,
        "max": rgb_max,
        "opacity": rgb_opacity,
    }
    composite_label = f"RGB Composite ({BAND_INFO[red_band].split('(')[0].strip()}, {BAND_INFO[green_band].split('(')[0].strip()}, {BAND_INFO[blue_band].split('(')[0].strip()})"
    m.addLayer(src_img, rgb_vis, composite_label)

m.add_layer_control()
m.to_streamlit(height=700)

# --- Legend info ---
with st.expander("Layer Descriptions"):
    st.markdown(
        """
| Band | Description |
|------|-------------|
| **exDmg** | Flood Damage - Annual Expected Damage (FD-AED). Fraction of structure value lost per year. |
| **exDmg_pros** | FD-AED with flood protection standards (FLOPROS) incorporated. |
| **exInunD** | Inundation Risk - Annual Expected Depth (IR-AED). Expected flood depth (m) per year. |
| **exInunD_pros** | IR-AED with flood protection standards incorporated. |
| **height** | Building height derived from global datasets. |
| **flopros_model** | FLOPROS modeled flood protection standard (return period in years). |
| **GDP-weighted** | Layer values multiplied by gridded GDP (PPP 2022 × population 2020). |
"""
    )
