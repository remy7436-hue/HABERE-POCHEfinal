import base64
from datetime import datetime, timedelta, timezone
from math import ceil, floor
import os
import re
import time
import zoneinfo
import altair as alt
import gspread
from google.oauth2.service_account import Credentials
import numpy as np
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import requests
import streamlit as st

# 1. Configuration de la page
st.set_page_config(
    page_title="Météo Habère-Poche", page_icon="🏔️", layout="wide"
)

# 2. Styles CSS personnalisés
st.markdown(
    """
    <style>
    .main {
        background-color: #f8fafc;
        padding: 0.5rem;
    }
    .stMetric {
        background-color: #ffffff;
        padding: 12px;
        border-radius: 12px;
        box-shadow: 0 2px 4px rgba(0,0,0,0.04);
        border: 1px solid #e2e8f0;
        margin-bottom: 8px;
    }
    @media (max-width: 768px) {
        .main .block-container {
            padding-left: 0.5rem !important;
            padding-right: 0.5rem !important;
            padding-top: 1rem !important;
        }
        [data-testid="stMetricValue"] {
            font-size: 1.4rem !important;
        }
        [data-testid="stMetricLabel"] {
            font-size: 0.85rem !important;
        }
        h1 { font-size: 1.5rem !important; }
        h2, h3 { font-size: 1.2rem !important; }
    }
    h1, h2, h3 {
        color: #1e293b;
        font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
    }
    </style>
""",
    unsafe_allow_html=True,
)

# 3. Récupération des secrets (Ecowitt + Google Sheets)
ECOWITT_API_KEY = st.secrets.get("ECOWITT_API_KEY", "")
ECOWITT_APP_KEY = st.secrets.get("ECOWITT_APP_KEY", "")
GW3000_MAC = st.secrets.get("GW3000_MAC", "")

SHEET_NAME = "Historique_Meteo_Habere_Poche"
SHEET_JOURNAL = "Journal_Observations"


# 4. Connexion et gestion Google Sheets
@st.cache_resource
def connecter_google_sheet():
    scope = [
        "https://www.googleapis.com/auth/spreadsheets",
        "https://www.googleapis.com/auth/drive",
    ]
    gcp_creds = dict(st.secrets["gcp_service_account"])

    if "private_key" in gcp_creds:
        key_val = str(gcp_creds["private_key"]).strip()
        if not key_val.startswith("-----BEGIN"):
            try:
                key_val = base64.b64decode(key_val).decode("utf-8")
            except Exception:
                pass
            gcp_creds["private_key"] = key_val.replace("\\n", "\n")

    creds = Credentials.from_service_account_info(gcp_creds, scopes=scope)
    client = gspread.authorize(creds)
    sheet = client.open(SHEET_NAME).sheet1
    return sheet


def connecter_feuille_journal():
    try:
        scope = [
            "https://www.googleapis.com/auth/spreadsheets",
            "https://www.googleapis.com/auth/drive",
        ]
        gcp_creds = dict(st.secrets["gcp_service_account"])
        if "private_key" in gcp_creds:
            key_val = str(gcp_creds["private_key"]).strip()
            if not key_val.startswith("-----BEGIN"):
                try:
                    key_val = base64.b64decode(key_val).decode("utf-8")
                except Exception:
                    pass
                gcp_creds["private_key"] = key_val.replace("\\n", "\n")
        creds = Credentials.from_service_account_info(gcp_creds, scopes=scope)
        client = gspread.authorize(creds)
        try:
            sheet_j = client.open(SHEET_NAME).worksheet(SHEET_JOURNAL)
        except Exception:
            sheet_j = client.open(SHEET_NAME).add_worksheet(
                title=SHEET_JOURNAL, rows=100, cols=3
            )
            sheet_j.append_row(["Date", "Auteur", "Observation"])
        return sheet_j
    except Exception:
        return None


def nettoyer_timestamp_robuste(valeur_brute):
    if pd.isna(valeur_brute):
        return pd.NaT
    s = str(valeur_brute).strip()
    match = re.search(r"(\d{4}-\d{2}-\d{2}[ T]\d{2}:\d{2}(?::\d{2})?)", s)
    if match:
        try:
            return pd.to_datetime(match.group(1))
        except Exception:
            pass
    return pd.to_datetime(s, errors="coerce")


@st.cache_data(ttl=300)
def charger_historique_gsheet():
    df_vide = pd.DataFrame(
        columns=[
            "timestamp",
            "heure",
            "temperature",
            "ressenti",
            "humidite",
            "pression",
            "pression_abs",
            "vent",
            "rafale",
            "direction",
            "pluie",
        ]
    )
    try:
        sheet = connecter_google_sheet()
        data = sheet.get_all_records()
        if data:
            df = pd.DataFrame(data)
            if not df.empty and "timestamp" in df.columns:
                df["timestamp"] = df["timestamp"].apply(
                    nettoyer_timestamp_robuste
                )
                df = df.dropna(subset=["timestamp"])

                if not df.empty:
                    cols_num = [
                        "temperature",
                        "ressenti",
                        "humidite",
                        "pression",
                        "pression_abs",
                        "vent",
                        "rafale",
                        "direction",
                        "pluie",
                    ]
                    for col in cols_num:
                        if col in df.columns:
                            df[col] = pd.to_numeric(df[col], errors="coerce")

                    df = df[
                        (
                            df["temperature"].between(-30, 50)
                            | df["temperature"].isna()
                        )
                        & (
                            df["pression"].between(900, 1100)
                            | df["pression"].isna()
                        )
                        & (
                            df["humidite"].between(0, 100)
                            | df["humidite"].isna()
                        )
                    ]

                    df = (
                        df.sort_values("timestamp")
                        .drop_duplicates(subset=["timestamp"])
                        .reset_index(drop=True)
                    )
                    if "pluie" not in df.columns:
                        df["pluie"] = 0.0
                    return df
    except Exception:
        pass

    return df_vide


def sauvegarder_mesure_gsheet(
    timestamp,
    heure,
    temp,
    ressenti,
    humidite,
    pression,
    pression_abs,
    vent,
    rafale,
    direction,
    pluie,
):
    df = charger_historique_gsheet()

    timestamp_propre = timestamp.replace(microsecond=0)
    actuel_temps = timestamp_propre.strftime("%Y-%m-%d %H:%M")

    if not df.empty and "timestamp" in df.columns:
        valid_ts = df["timestamp"].dropna()
        if not valid_ts.empty:
            dernier_temps = pd.to_datetime(valid_ts.iloc[-1]).strftime(
                "%Y-%m-%d %H:%M"
            )
            if dernier_temps == actuel_temps:
                return df

    nouvelle_ligne = [
        timestamp_propre.strftime("%Y-%m-%d %H:%M:%S"),
        heure,
        temp,
        ressenti,
        humidite,
        pression,
        pression_abs,
        vent,
        rafale,
        direction,
        pluie,
    ]

    try:
        sheet = connecter_google_sheet()
        sheet.append_row(nouvelle_ligne)
        st.cache_data.clear()
    except Exception:
        pass

    nouvelle_df = pd.DataFrame([
        {
            "timestamp": timestamp_propre,
            "heure": heure,
            "temperature": temp,
            "ressenti": ressenti,
            "humidite": humidite,
            "pression": pression,
            "pression_abs": pression_abs,
            "vent": vent,
            "rafale": rafale,
            "direction": direction,
            "pluie": pluie,
        }
    ])
    df = pd.concat([df, nouvelle_df], ignore_index=True)
    return df


# 5. Fonctions utilitaires & calculs
def to_float(val):
    if val is None or val == "":
        return 0.0
    if isinstance(val, (int, float)):
        return float(val)
    s = str(val).lower()
    for unit in ["°c", "°f", "km/h", "mph", "hpa", "inhg", "in", "mm", "%"]:
        s = s.replace(unit, "")
    s = s.replace(",", ".").strip()
    try:
        return float(s)
    except ValueError:
        return 0.0


def degres_vers_cardinal(deg):
    if deg is None or pd.isna(deg):
        return "N/A"
    try:
        dirs = [
            "N",
            "NNE",
            "NE",
            "ENE",
            "E",
            "ESE",
            "SE",
            "SSE",
            "S",
            "SSO",
            "SO",
            "OSO",
            "O",
            "ONO",
            "NO",
            "NNO",
        ]
        return dirs[int((float(deg) + 11.25) / 22.5) % 16]
    except Exception:
        return "N/A"


def interpreter_vent_local(dir_deg, speed):
    if dir_deg is None or pd.isna(dir_deg):
        return "Direction du vent non disponible.", "🧭"

    d = float(dir_deg) % 360
    if speed < 1.5:
        return "Conditions calmes, pas d'influence dynamique notable.", "🟢"
    elif 30 <= d <= 80:
        return (
            "Flux de Nord-Est / Est : Tendance à la bise locale, temps souvent"
            " plus sec et dégagé sur les reliefs."
        ), "🌬️"
    elif 140 <= d <= 220:
        return (
            "Flux de Sud / Sud-Ouest : Remontées douces, humidité potentielle en"
            " provenance de la vallée."
        ), "↗️"
    elif 270 <= d <= 330:
        return (
            "Flux de Nord-Ouest / Ouest : Passage de masses d'air instables,"
            " risque d'averses sur les Préalpes."
        ), "🌧️"
    else:
        return (
            f"Flux sectoriel orienté au {degres_vers_cardinal(d)} ({int(d)}°),"
            " régime classique de moyenne montagne."
        ), "💨"


def calculer_base_cumulus(temp, humidite, altitude_station=900):
    if temp is None or humidite is None or humidite <= 0:
        return None, None
    try:
        t, rh = float(temp), float(humidite)
        alpha = ((17.27 * t) / (237.7 + t)) + np.log(rh / 100.0)
        dew_point = (237.7 * alpha) / (17.27 - alpha)
        base_sol = (t - dew_point) * 125.0
        return round(base_sol), round(base_sol + altitude_station)
    except Exception:
        return None, None


def calculer_ressenti(temp, wind_speed_kmh, humidite):
    if temp is None:
        return None, "Indisponible"
    if temp <= 10.0 and wind_speed_kmh and wind_speed_kmh > 4.8:
        wc = (
            13.12
            + 0.6215 * temp
            - 11.37 * (wind_speed_kmh**0.16)
            + 0.3965 * temp * (wind_speed_kmh**0.16)
        )
        return round(wc, 1), "Windchill (Vent)"
    elif temp >= 20.0 and humidite:
        alpha = ((17.27 * temp) / (237.7 + temp)) + np.log(humidite / 100.0)
        dew_point = (237.7 * alpha) / (17.27 - alpha)
        e = 6.11 * np.exp(
            5417.7530 * ((1 / 273.16) - (1 / (273.15 + dew_point)))
        )
        return round(temp + (5 / 9) * (e - 10), 1), "Humidex (Moiteur)"
    return temp, "Standard"


def analyser_risques_montagne(temp, humidite, pression):
    if temp is None or humidite is None:
        return "Indisponible", 0.1, 0.0
    alpha = ((17.27 * temp) / (237.7 + temp)) + np.log(max(humidite, 1) / 100.0)
    dew_point = (237.7 * alpha) / (17.27 - alpha)
    risque = (
        "🚨 Risque de gel imminent !"
        if temp <= 2.0
        else (
            "⚠️ Risque de gelée blanche"
            if temp <= 5.0 and dew_point <= 2.0
            else "✅ Pas de risque de gel"
        )
    )
    etp = max(
        0.1, round(0.0023 * (temp + 17.8) * (100 - humidite) ** 0.5 * 5, 2)
    )
    return risque, etp, round(dew_point, 1)


def calculer_tendance_et_prevision_robuste(df_hist, pression_actuelle):
    if (
        df_hist is None
        or len(df_hist) < 2
        or "timestamp" not in df_hist.columns
    ):
        return (
            0.0,
            "Stable (données insuffisantes)",
            "Données barométriques en cours d'accumulation.",
            "Analyse en attente",
        )

    df_t = df_hist.dropna(subset=["timestamp", "pression"]).copy()
    if len(df_t) < 2:
        return (
            0.0,
            "Stable",
            (
                "☀️ Temps beau, stable et sec"
                if pression_actuelle >= 1025
                else "☁️ Temps changeant"
            ),
            "Stabilité correcte",
        )

    dernier_temps = df_t["timestamp"].iloc[-1]
    limite_3h = dernier_temps - pd.Timedelta(hours=3)

    df_3h = df_t[df_t["timestamp"] <= limite_3h]
    pression_ref = (
        df_3h["pression"].iloc[-1]
        if not df_3h.empty
        else df_t["pression"].iloc[0]
    )

    tendance_3h = round(float(pression_actuelle - pression_ref), 2)

    if tendance_3h >= 1.5:
        libelle_tendance = f"Forte hausse (+{tendance_3h} hPa / 3h) 📈"
    elif 0.5 <= tendance_3h < 1.5:
        libelle_tendance = f"Hausse lente (+{tendance_3h} hPa / 3h) ↗️"
    elif -0.5 <= tendance_3h < 0.5:
        libelle_tendance = f"Stable ({tendance_3h:+0.1f} hPa / 3h) ➡️"
    elif -1.5 < tendance_3h <= -0.5:
        libelle_tendance = f"Baisse modérée ({tendance_3h} hPa / 3h) ↘️"
    else:
        libelle_tendance = f"Forte baisse ({tendance_3h} hPa / 3h) 📉"

    if tendance_3h >= 1.0:
        prevision = (
            "☀️ Amélioration durable, conditions anticycloniques robustes."
            if pression_actuelle >= 1015
            else "🌤️ Hausse barométrique, accalmie progressive en vue."
        )
        indice_confiance = "Élevée (Anticyclonique)"
    elif tendance_3h <= -1.0:
        prevision = (
            "🌧️ Dégradation marquée confirmée, approche d'une perturbation"
            " active."
            if pression_actuelle < 1015
            else "⚠️ Baisse rapide de pression, changement de temps imminent."
        )
        indice_confiance = "Élevée (Passage perturbé)"
    else:
        if pression_actuelle >= 1020:
            prevision = (
                "☀️ Temps stable, sec et bien installé sur le secteur de la"
                " Vallée Verte."
            )
            indice_confiance = "Moyenne à Haute"
        elif pression_actuelle <= 1005:
            prevision = (
                "☁️ Conditions dépressionnaires persistantes, passages nuageux"
                " fréquents."
            )
            indice_confiance = "Moyenne"
        else:
            prevision = (
                "☁️ Temps variable et de saison, alternance d'éclaircies."
            )
            indice_confiance = "Modérée (Variable)"

    return tendance_3h, libelle_tendance, prevision, indice_confiance


def obtenir_normales_saison(mois):
    normales = {
        1: {"t_min": -3.0, "t_max": 3.0, "desc": "Hiver frais, neige fréquente."},
        2: {"t_min": -2.5, "t_max": 4.5, "desc": "Hiver persistant, gel matinal."},
        3: {"t_min": 0.0, "t_max": 9.0, "desc": "Début de transition printanière."},
        4: {"t_min": 3.0, "t_max": 13.0, "desc": "Printemps variable, giboulées."},
        5: {"t_min": 7.0, "t_max": 17.5, "desc": "Douceur printanière, verdissement."},
        6: {"t_min": 10.5, "t_max": 21.5, "desc": "Début d'été montagnard agréable."},
        7: {"t_min": 12.5, "t_max": 24.0, "desc": "Chaleur estivale modérée à 900m."},
        8: {"t_min": 12.0, "t_max": 23.5, "desc": "Période estivale stable, orages."},
        9: {"t_min": 8.5, "t_max": 18.5, "desc": "Automne précoce, nuits fraîches."},
        10: {"t_min": 5.0, "t_max": 13.0, "desc": "Saison des brumes et des pluies."},
        11: {"t_min": 0.5, "t_max": 6.5, "desc": "Premières neiges de basse montagne."},
        12: {"t_min": -2.0, "t_max": 3.5, "desc": "Ambiance hivernale au village."},
    }
    return normales.get(
        mois,
        {"t_min": 5.0, "t_max": 15.0, "desc": "Normales de saison standard."},
    )


# 6. Récupération API Ecowitt
def fetch_ecowitt_data(app_key, api_key, mac):
    url = "https://api.ecowitt.net/api/v3/device/real_time"
    params = {
        "application_key": app_key,
        "api_key": api_key,
        "mac": mac,
        "call_by": "all",
        "unit": "1",
    }
    try:
        res = requests.get(url, params=params, timeout=8)
        if res.status_code == 200:
            return res.json()
    except Exception:
        pass
    return None


# Sidebar
with st.sidebar:
    st.header("⚙️ Station Météo — Cloud")
    st.write("**Altitude :** 900 m (Habère-Poche)")
    st.markdown("---")
    lissage_active = st.checkbox(
        "Lissage vectoriel 3h (Rose des Vents)", value=True
    )

    if st.button("🔄 Forcer la synchro & Actualiser"):
        st.cache_data.clear()
        st.rerun()

st.title("🏔️ Station Météo — Habère-Poche")

raw_data = fetch_ecowitt_data(ECOWITT_APP_KEY, ECOWITT_API_KEY, GW3000_MAC)
if not raw_data or raw_data.get("code") != 0:
    st.error("Impossible de récupérer les données depuis l'API Ecowitt.")
    st.stop()

ds = raw_data.get("data", {})


def get_val(group, key):
    node = ds.get(group, {}).get(key, {})
    val = node.get("value", 0.0) if isinstance(node, dict) else node
    return to_float(val)


temp_brute = get_val("outdoor", "temperature")
temp = round((temp_brute - 32.0) * 5.0 / 9.0, 1)

humidity = get_val("outdoor", "humidity")

pressure = get_val("pressure", "relative")
if pressure < 50:
    pressure = round(pressure * 33.8639, 1)

pressure_abs = get_val("pressure", "absolute")
if pressure_abs < 50:
    pressure_abs = round(pressure_abs * 33.8639, 1)

wind_speed = get_val("wind", "wind_speed")
wind_gust = get_val("wind", "wind_gust")
wind_dir = get_val("wind", "wind_direction")

rain_day = get_val("rainfall", "day") or get_val("rainfall", "daily") or 0.0
rain_month = get_val("rainfall", "month") or get_val("rainfall", "monthly") or 0.0
rain_year = get_val("rainfall", "year") or get_val("rainfall", "yearly") or 0.0

base_sol, altitude_mer = calculer_base_cumulus(temp, humidity, 900)
temp_ressentie, mode_ressenti = calculer_ressenti(temp, wind_speed, humidity)
risque_gel, etp_val, point_rosee = analyser_risques_montagne(
    temp, humidity, pressure
)

try:
    tz_paris = zoneinfo.ZoneInfo("Europe/Paris")
except Exception:
    tz_paris = timezone(timedelta(hours=2))

current_timestamp = datetime.now(tz_paris)
current_time_str = current_timestamp.strftime("%H:%M:%S")

df_hist = sauvegarder_mesure_gsheet(
    current_timestamp,
    current_time_str,
    temp,
    temp_ressentie,
    humidity,
    pressure,
    pressure_abs,
    wind_speed,
    wind_gust,
    wind_dir,
    rain_day,
)

if not df_hist.empty and "timestamp" in df_hist.columns:
    df_hist["timestamp"] = df_hist["timestamp"].apply(nettoyer_timestamp_robuste)

delta_temp = (
    round(
        float(df_hist.iloc[-1]["temperature"])
        - float(df_hist.iloc[-2]["temperature"]),
        1,
    )
    if len(df_hist) >= 2
    else 0.0
)
delta_hum = (
    round(
        float(df_hist.iloc[-1]["humidite"])
        - float(df_hist.iloc[-2]["humidite"]),
        1,
    )
    if len(df_hist) >= 2
    else 0.0
)
delta_press = (
    round(
        float(df_hist.iloc[-1]["pression"])
        - float(df_hist.iloc[-2]["pression"]),
        2,
    )
    if len(df_hist) >= 2
    else 0.0
)

# Extrêmes du jour
max_temp, min_temp, max_temp_time, min_temp_time = "--", "--", "", ""
max_wind, max_gust = 0.0, 0.0

if not df_hist.empty and "timestamp" in df_hist.columns:
    df_calc = df_hist.copy()
    df_calc["timestamp"] = pd.to_datetime(df_calc["timestamp"], errors="coerce")

    date_aujourdhui = current_timestamp.date()
    df_today = df_calc[df_calc["timestamp"].dt.date == date_aujourdhui].copy()

    if df_today.empty:
        df_today = df_calc

    df_today["temperature"] = pd.to_numeric(
        df_today["temperature"], errors="coerce"
    )
    df_today_clean = df_today.dropna(subset=["temperature"])
    df_today_clean = df_today_clean[
        df_today_clean["temperature"].between(-30, 50)
    ]

    if not df_today_clean.empty:
        idx_max = df_today_clean["temperature"].idxmax()
        idx_min = df_today_clean["temperature"].idxmin()

        max_temp = round(float(df_today_clean.loc[idx_max, "temperature"]), 1)
        min_temp = round(float(df_today_clean.loc[idx_min, "temperature"]), 1)

        ts_max = df_today_clean.loc[idx_max, "timestamp"]
        ts_min = df_today_clean.loc[idx_min, "timestamp"]

        max_temp_time = (
            ts_max.strftime("%H:%M:%S")
            if pd.notna(ts_max)
            else df_today_clean.loc[idx_max, "heure"]
        )
        min_temp_time = (
            ts_min.strftime("%H:%M:%S")
            if pd.notna(ts_min)
            else df_today_clean.loc[idx_min, "heure"]
        )

    max_wind = pd.to_numeric(df_today["vent"], errors="coerce").max()
    max_gust = pd.to_numeric(df_today["rafale"], errors="coerce").max()
    max_wind = round(float(max_wind), 1) if pd.notna(max_wind) else 0.0
    max_gust = round(float(max_gust), 1) if pd.notna(max_gust) else 0.0

tendance_val, tendance_libelle, prevision_texte, indice_confiance = (
    calculer_tendance_et_prevision_robuste(df_hist, pressure)
)


# 7. Structure par Onglets
tab1, tab2, tab3, tab4, tab5, tab6, tab7, tab8 = st.tabs([
    "📊 Temps Réel & Extrêmes",
    "🧭 Rose des Vents",
    "🌧️ Pluviométrie",
    "☁️ Plancher Nuageux",
    "📈 Historique & Tendances",
    "💡 Prévisions & Analyse",
    "📓 Journal de Bord & Climat",
    "🌐 Radar Météo & Pluie (Windy)",
])

with tab1:
    st.subheader("📡 Conditions Actuelles (Flux Ecowitt Cloud)")
    with st.container(border=True):
        c1, c2, c3, c4 = st.columns(4)
        c1.metric("Température", f"{temp} °C", delta=f"{delta_temp:+.1f} °C")
        c2.metric("Humidité", f"{humidity} %", delta=f"{delta_hum:+.1f} %")
        c3.metric(
            "Pression relative",
            f"{pressure} hPa",
            delta=f"{delta_press:+.2f} hPa",
        )
        c4.metric("Pression absolue", f"{pressure_abs} hPa")

        st.markdown("---")
        c5, c6, c7, c8 = st.columns(4)
        c5.metric("Ressenti", f"{temp_ressentie} °C", help=mode_ressenti)
        c6.metric("Vent moyen", f"{wind_speed} km/h")
        c7.metric("Rafale", f"{wind_gust} km/h")
        c8.metric(
            "Direction", f"{degres_vers_cardinal(wind_dir)} ({int(wind_dir)}°)"
        )

        st.markdown("---")
        c5_b, _ = st.columns(2)
        c5_b.metric("Pluie du jour", f"{rain_day} mm")

    st.subheader("🏆 Extrêmes du jour")
    with st.container(border=True):
        e1, e2, e3, e4 = st.columns(4)
        e1.metric(
            "Max Chaleur (Tx)",
            f"{max_temp} °C" if max_temp != "--" else "--",
            f"à {max_temp_time}",
        )
        e2.metric(
            "Min Fraîcheur (Tn)",
            f"{min_temp} °C" if min_temp != "--" else "--",
            f"à {min_temp_time}",
        )
        e3.metric("Vent max", f"{max_wind} km/h")
        e4.metric("Rafale max", f"{max_gust} km/h")
    st.caption(
        f"Synchro cloud : **{current_time_str}** | Lignes enregistrées :"
        f" **{len(df_hist)}**"
    )

with tab2:
    st.subheader("🧭 Rose des Vents Améliorée (Google Sheet)")
    vent_analyse_texte, vent_icone = interpreter_vent_local(
        wind_dir, wind_speed
    )
    st.info(f"**Analyse du flux actuel :** {vent_icone} {vent_analyse_texte}")

    if not df_hist.empty and "direction" in df_hist.columns:
        df_rose = df_hist.dropna(subset=["direction", "vent"]).copy()
        df_rose["vent"] = pd.to_numeric(df_rose["vent"], errors="coerce")
        df_rose["direction"] = pd.to_numeric(
            df_rose["direction"], errors="coerce"
        )
        df_rose = df_rose.dropna(subset=["direction", "vent"])

        if not df_rose.empty:
            if lissage_active and len(df_rose) > 5:
                df_rose = df_rose.set_index("timestamp")
                rads = np.radians(df_rose["direction"])
                df_rose["u"] = -df_rose["vent"] * np.sin(rads)
                df_rose["v"] = -df_rose["vent"] * np.cos(rads)

                r_win = df_rose.rolling(window="3h")
                df_rose["vent"] = r_win["vent"].mean()
                u_s = r_win["u"].mean()
                v_s = r_win["v"].mean()

                smoothed_rad = np.arctan2(-u_s, -v_s)
                df_rose["direction"] = (np.degrees(smoothed_rad) + 360) % 360
                df_rose = df_rose.reset_index().dropna(
                    subset=["direction", "vent"]
                )

            calm_count = len(df_rose[df_rose["vent"] < 1])
            total_count = len(df_rose)
            calm_percentage = (
                (calm_count / total_count * 100) if total_count > 0 else 0
            )

            bins_vitesse = [0, 5, 10, 15, 20, 30, 40, 50, 150]
            labels_vitesse = [
                "< 5",
                "5-10",
                "10-15",
                "15-20",
                "20-30",
                "30-40",
                "40-50",
                "> 50",
            ]
            df_rose["vent_tranche"] = pd.cut(
                df_rose["vent"],
                bins=bins_vitesse,
                labels=labels_vitesse,
                right=False,
            )

            bins_dir = [-11.25 + i * 22.5 for i in range(17)]
            labels_deg = [i * 22.5 for i in range(16)]
            noms_secteurs = [
                "N",
                "NNE",
                "NE",
                "ENE",
                "E",
                "ESE",
                "SE",
                "SSE",
                "S",
                "SSO",
                "SO",
                "OSO",
                "O",
                "ONO",
                "NO",
                "NNO",
            ]

            df_rose["bin_deg"] = pd.cut(
                df_rose["direction"] % 360,
                bins=bins_dir,
                labels=labels_deg,
                include_lowest=True,
            )
            df_rose["bin_deg"] = df_rose["bin_deg"].astype(float)

            df_grp = (
                df_rose.groupby(["bin_deg", "vent_tranche"], observed=False)
                .size()
                .reset_index(name="count")
            )

            deg_to_nom = dict(zip(labels_deg, noms_secteurs))
            df_grp["nom"] = df_grp["bin_deg"].map(deg_to_nom)

            fig_rose = px.bar_polar(
                df_grp,
                r="count",
                theta="bin_deg",
                color="vent_tranche",
                color_discrete_sequence=px.colors.sequential.Blues,
                template="plotly_white",
            )

            titre_rose = f"Rose des Vents (Vents calmes : {calm_percentage:.1f}%"
            if lissage_active:
                titre_rose += " — Lissé 3h"
            titre_rose += ")"

            fig_rose.update_layout(
                title=titre_rose,
                polar=dict(
                    angularaxis=dict(
                        tickvals=labels_deg,
                        ticktext=noms_secteurs,
                        direction="clockwise",
                        rotation=90,
                    ),
                    radialaxis=dict(showticklabels=True, ticks=""),
                ),
                height=320,
                margin=dict(l=10, r=10, t=40, b=10),
            )
            st.plotly_chart(fig_rose, use_container_width=True)

with tab3:
    st.subheader("🌧️ Suivi de la Pluviométrie")
    c_p1, c_p2, c_p3 = st.columns(3)
    c_p1.metric("Pluie du jour", f"{rain_day} mm")
    c_p2.metric("Pluie du mois", f"{rain_month} mm")
    c_p3.metric("Pluie annuelle", f"{rain_year} mm")

    st.markdown("---")

    if not df_hist.empty and "pluie" in df_hist.columns:
        df_rain = df_hist.copy()
        df_rain["pluie"] = pd.to_numeric(
            df_rain["pluie"], errors="coerce"
        ).fillna(0.0)
        df_rain["date_seule"] = df_rain["timestamp"].dt.date
        df_journalier = (
            df_rain.groupby("date_seule")["pluie"].max().reset_index()
        )

        fig_rain = px.bar(
            df_journalier,
            x="date_seule",
            y="pluie",
            title="Cumul journalier de précipitations (mm)",
        )
        fig_rain.update_layout(
            height=300,
            margin=dict(l=10, r=10, t=40, b=10),
            template="plotly_white",
        )
        st.plotly_chart(fig_rain, use_container_width=True)
    else:
        st.info("En attente de données de pluie...")

with tab4:
    st.subheader("🏔️ Plancher Nuageux sur les Reliefs")
    if base_sol is not None and altitude_mer is not None:
        cp1, cp2 = st.columns(2)
        cp1.metric("Base des nuages (sol)", f"{base_sol} m")
        cp2.metric("Altitude / Mer (Habère-Poche)", f"{altitude_mer} m")

        st.markdown("---")
        st.write("**Repères topographiques locaux :**")

        sommets = [
            ("Station Habère-Poche", 900),
            ("Col de Terramont", 1100),
            ("Mont Hirmentaz", 1607),
            ("Mont Forchat", 1539),
        ]

        for nom, alt_sommet in sommets:
            if altitude_mer <= alt_sommet:
                st.caption(
                    f"🌫️ **{nom}** ({alt_sommet} m) : Potentiellement dans les"
                    " nuages ou le brouillard."
                )
            else:
                st.caption(
                    f"☀️ **{nom}** ({alt_sommet} m) : Au-dessus du plancher"
                    " nuageux estimé."
                )
    else:
        st.warning("Données insuffisantes pour estimer la base des nuages.")

with tab5:
    st.subheader("📈 Historique & Tendances Barométriques")
    if not df_hist.empty:
        # 1. Températures
        fig_temp = px.line(
            df_hist,
            x="timestamp",
            y=["temperature", "ressenti"],
            title="Évolution des Températures (°C)",
            labels={"value": "Température °C", "variable": "Légende"},
        )
        fig_temp.update_layout(height=280, template="plotly_white")
        st.plotly_chart(fig_temp, use_container_width=True)

        # 2. Pression
        fig_press = px.line(
            df_hist,
            x="timestamp",
            y="pression",
            title="Évolution de la Pression Relative (hPa)",
        )
        fig_press.update_layout(height=280, template="plotly_white")
        st.plotly_chart(fig_press, use_container_width=True)

        # 3. Vent & Rafales (Inclus)
        if "vent" in df_hist.columns and "rafale" in df_hist.columns:
            fig_wind = px.line(
                df_hist,
                x="timestamp",
                y=["vent", "rafale"],
                title="Évolution du Vent Moyen et des Rafales (km/h)",
                labels={"value": "Vitesse (km/h)", "variable": "Mesure"},
            )
            fig_wind.update_layout(height=280, template="plotly_white")
            st.plotly_chart(fig_wind, use_container_width=True)
    else:
        st.info("Historique en cours de constitution.")

with tab6:
    st.subheader("💡 Prévisions & Analyse Régionale")
    with st.container(border=True):
        st.markdown(f"### **Tendance :** {tendance_libelle}")
        st.write(f"**Prévision :** {prevision_texte}")
        st.caption(f"Indice de confiance : {indice_confiance}")

    st.markdown("---")
    st.subheader("⚠️ Analyse des Risques Locaux")
    r1, r2, r3 = st.columns(3)
    r1.metric("Risque de Gel", risque_gel)
    r2.metric("Point de Rosée", f"{point_rosee} °C")
    r3.metric("ETP estimée", f"{etp_val} mm/j")

with tab7:
    st.subheader("📓 Journal de Bord & Climatologie")
    mois_actuel = current_timestamp.month
    normale = obtenir_normales_saison(mois_actuel)

    st.markdown(f"### Normales de Saison (Mois {mois_actuel})")
    cn1, cn2 = st.columns(2)
    cn1.metric("Température Min Normale", f"{normale['t_min']} °C")
    cn2.metric("Température Max Normale", f"{normale['t_max']} °C")
    st.caption(normale["desc"])

    st.markdown("---")
    st.write("**Nouveau message au journal :**")

    sheet_journal = connecter_feuille_journal()
    with st.form("form_journal"):
        auteur = st.text_input("Auteur", "Rémi")
        obs = st.text_area("Observation météo / jardin")
        btn_submit = st.form_submit_button("Saisir la remarque")

        if btn_submit and obs:
            if sheet_journal:
                sheet_journal.append_row(
                    [
                        current_timestamp.strftime("%Y-%m-%d %H:%M"),
                        auteur,
                        obs,
                    ]
                )
                st.success("Remarque enregistrée avec succès !")
            else:
                st.error("Erreur d'accès au Google Sheet Journal.")

with tab8:
    st.subheader("🌐 Radar Météo & Pluie (Windy)")
    st.components.v1.iframe(
        "https://embed.windy.com/embed.html?type=map&location=coordinates&metricRain=mm&metricTemp=%C2%B0C&metricWind=km%2Fh&zoom=10&overlay=rain&product=ecmwf&level=surface&lat=46.262&lon=6.471",
        height=500,
    )
