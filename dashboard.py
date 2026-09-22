import base64
from datetime import datetime, timedelta, timezone
from math import ceil, floor, log
import os
import re
import time
import zoneinfo

import altair as alt
from google.oauth2.service_account import Credentials
import gspread
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

# 2. Application de styles CSS personnalisés
st.markdown(
    """
    <style>
    /* Fond général */
    .main {
        background-color: #f8fafc;
        padding: 0.5rem;
    }

    /* Adaptabilité cartes/metrics */
    .stMetric {
        background-color: #ffffff;
        padding: 12px;
        border-radius: 12px;
        box-shadow: 0 2px 4px rgba(0,0,0,0.04);
        border: 1px solid #e2e8f0;
        margin-bottom: 8px;
    }

    /* Responsive mobile tuning */
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
        h1 {
            font-size: 1.5rem !important;
        }
        h2, h3 {
            font-size: 1.2rem !important;
        }
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


# 4. Connexion au Google Sheet
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


# 5. Fonctions utilitaires, calculs physiques & prévisions
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
    if temp is None or humidite is None:
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


def calculate_dew_point(temp: float, humidity: float):
    if temp is None or humidity is None or pd.isna(temp) or pd.isna(humidity):
        return None
    try:
        t, rh = float(temp), float(humidity)
        a, b = 17.27, 237.7
        alpha = ((a * t) / (b + t)) + log(rh / 100.0)
        return round((b * alpha) / (a - alpha), 1)
    except Exception:
        return None


def get_fitzroy_forecast(delta_p_3h: float) -> dict:
    if delta_p_3h is None or pd.isna(delta_p_3h):
        return {
            "status": "Données insuffisantes",
            "icon": "⚪",
            "desc": "Historique < 3h",
        }

    if delta_p_3h <= -3.0:
        return {
            "status": "Tempête / Perturbation majeure",
            "icon": "⛈️",
            "desc": "Chute brutale de pression",
        }
    elif -3.0 < delta_p_3h <= -1.2:
        return {
            "status": "Dégradation / Pluie probable",
            "icon": "🌧️",
            "desc": "Baisse significative",
        }
    elif -1.2 < delta_p_3h < 1.2:
        return {
            "status": "Temps stable / Maintien",
            "icon": "🌤️",
            "desc": "Pression quasi constante",
        }
    elif 1.2 <= delta_p_3h < 3.0:
        return {
            "status": "Amélioration / Temps plus sec",
            "icon": "🌤️",
            "desc": "Hausse régulière",
        }
    else:
        return {
            "status": "Beau temps durable / Anticyclone",
            "icon": "☀️",
            "desc": "Forte hausse barométrique",
        }


def get_combined_rules_forecast(
    temp: float, humidity: float, pressure: float, delta_p_3h: float, wind_dir: float
) -> dict:
    if any(
        v is None or pd.isna(v)
        for v in [temp, humidity, pressure, delta_p_3h, wind_dir]
    ):
        return {
            "summary": "Mesures insuffisantes pour l'analyse locale avancée.",
            "level": "info",
        }

    is_sw_sector = 180 <= wind_dir <= 270
    is_ne_sector = (0 <= wind_dir <= 90) or (wind_dir >= 315)

    if delta_p_3h < -1.0 and humidity > 80 and is_sw_sector:
        return {
            "summary": "Risque élevé de précipitations continues (Front humide du Sud-Ouest).",
            "level": "warning",
        }
    elif delta_p_3h > 0.8 and humidity < 60 and is_ne_sector:
        return {
            "summary": "Conditions sèches et éclaircies durables (Flux de Bise / Nord-Est).",
            "level": "success",
        }
    elif temp <= 3.0 and humidity > 85 and delta_p_3h < 0:
        return {
            "summary": "Attention : Risque de neige ou pluie mêlée à 900m d'altitude.",
            "level": "warning",
        }
    else:
        return {
            "summary": "Pas de changement brutal détecté. Stabilité selon profil barométrique.",
            "level": "info",
        }


def analyser_risques_montagne(temp, humidite, pression):
    if temp is None or humidite is None:
        return "Indisponible", 0.1, 0.0
    dew_point = calculate_dew_point(temp, humidite) or 0.0
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
    return risque, etp, dew_point


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
    if not df_3h.empty:
        pression_ref = df_3h["pression"].iloc[-1]
    else:
        pression_ref = df_t["pression"].iloc[0]

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
                "☀️ Temps stable, sec et bien établi sur le secteur de la"
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
        st.rerun()

st.title("🏔️ Station Météo — Habère-Poche")

raw_data = fetch_ecowitt_data(ECOWITT_APP_KEY, ECOWITT_API_KEY, GW3000_MAC)
if not raw_data or raw_data.get("code") != 0:
    st.error(
        "Impossible de récupérer les données depuis l'API Ecowitt. Vérifie tes"
        " clés."
    )
    st.stop()

ds = raw_data.get("data", {})


def get_val(group, key):
    node = ds.get(group, {}).get(key, {})
    if isinstance(node, dict):
        val = node.get("value", 0.0)
    else:
        val = node
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

rain_day = get_val("rainfall", "day")
if rain_day == 0.0:
    rain_day = (
        get_val("rainfall", "daily")
        or get_val("precipitation", "rain_day")
        or get_val("rain", "day")
    )

rain_month = get_val("rainfall", "month")
if rain_month == 0.0:
    rain_month = get_val("rainfall", "monthly") or get_val("rain", "month")

rain_year = get_val("rainfall", "year")
if rain_year == 0.0:
    rain_year = get_val("rainfall", "yearly") or get_val("rain", "year")

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


# 7. Structure des 8 onglets
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
        f"Synchro cloud : **{current_time_str}** | Lignes Google Sheet :"
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
                "< 5", "5-10", "10-15", "15-20", "20-30", "30-40", "40-50", "> 50"
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
                "N", "NNE", "NE", "ENE", "E", "ESE", "SE", "SSE",
                "S", "SSO", "SO", "OSO", "O", "ONO", "NO", "NNO"
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
    if base_sol is not None:
        c1, c2, c3 = st.columns(3)
        c1.metric("Altitude village", "900 m")
        c2.metric("Base des nuages / sol", f"+{base_sol} m")
        c3.metric("Altitude absolue", f"{altitude_mer} m")

        fig_pano = go.Figure()
        img_path = "PXL_20260913_173725056.MP.jpg"
        if os.path.exists(img_path):
            with open(img_path, "rb") as f:
                img_data = base64.b64encode(f.read()).decode("utf-8")
                fig_pano.add_layout_image(
                    dict(
                        source=f"data:image/jpeg;base64,{img_data}",
                        xref="x",
                        yref="y",
                        x=0,
                        y=2000,
                        sizex=10,
                        sizey=1100,
                        sizing="stretch",
                        opacity=0.85,
                        layer="below",
                    )
                )

        fig_pano.add_shape(
            type="line",
            x0=0,
            y0=altitude_mer,
            x1=10,
            y1=altitude_mer,
            line=dict(color="LightSkyBlue", width=3, dash="dashdot"),
        )
        fig_pano.add_annotation(
            x=5,
            y=altitude_mer,
            text=f"Plancher Cloud Base: {altitude_mer} m",
            showarrow=True,
            arrowhead=1,
            bgcolor="rgba(255, 255, 255, 0.8)",
        )

        fig_pano.update_layout(
            xaxis=dict(range=[0, 10], visible=False),
            yaxis=dict(range=[900, 2000], title="Altitude (m)"),
            height=400,
            margin=dict(l=20, r=20, t=30, b=20),
            template="plotly_white",
        )
        st.plotly_chart(fig_pano, use_container_width=True)
    else:
        st.info("Calcul du plancher nuageux indisponible.")

with tab5:
    st.subheader("📈 Historique & Tendances Récentes")
    if not df_hist.empty and len(df_hist) >= 2:
        df_plot = df_hist.copy()

        fig_temp = px.line(
            df_plot,
            x="timestamp",
            y=["temperature", "ressenti"],
            labels={"value": "°C", "timestamp": "Heure"},
            title="Évolution de la Température & Ressenti",
        )
        fig_temp.update_layout(
            height=300,
            margin=dict(l=10, r=10, t=40, b=10),
            template="plotly_white",
        )
        st.plotly_chart(fig_temp, use_container_width=True)

        fig_press = px.line(
            df_plot,
            x="timestamp",
            y="pression",
            labels={"pression": "hPa", "timestamp": "Heure"},
            title="Tendance Barométrique (Pression Relative)",
        )
        fig_press.update_layout(
            height=250,
            margin=dict(l=10, r=10, t=40, b=10),
            template="plotly_white",
        )
        st.plotly_chart(fig_press, use_container_width=True)
    else:
        st.info(
            "Historique en cours de constitution (nécessite au moins 2 mesures)."
        )

with tab6:
    st.subheader("💡 Prévisions & Analyse Locale Advanced")

    f_res = get_fitzroy_forecast(tendance_val)
    r_res = get_combined_rules_forecast(
        temp, humidity, pressure, tendance_val, wind_dir
    )

    col_a, col_b = st.columns(2)
    with col_a:
        with st.container(border=True):
            st.markdown("### 📜 Règle de FitzRoy")
            st.markdown(f"## {f_res['icon']} {f_res['status']}")
            st.caption(f_res["desc"])

    with col_b:
        with st.container(border=True):
            st.markdown("### 🎯 Analyse Combinée")
            if r_res["level"] == "warning":
                st.warning(r_res["summary"])
            elif r_res["level"] == "success":
                st.success(r_res["summary"])
            else:
                st.info(r_res["summary"])

    st.markdown("---")
    st.markdown("### ⛰️ Risques & Paramètres de Montagne")
    m1, m2, m3 = st.columns(3)
    m1.metric("Risque Gel", risque_gel)
    m2.metric("Point de Rosée", f"{point_rosee} °C")
    m3.metric("ETP Estimée", f"{etp_val} mm/j")

with tab7:
    st.subheader("📓 Journal de Bord & Climatologie")

    normales = obtenir_normales_saison(current_timestamp.month)
    st.markdown(
        f"**Normales de saison ({current_timestamp.strftime('%B')}) :** "
        f"Tn {normales['t_min']}°C | Tx {normales['t_max']}°C — *{normales['desc']}*"
    )

    st.markdown("---")
    st.markdown("### ✍️ Ajouter une Observation")

    sheet_j = connecter_feuille_journal()
    with st.form("form_journal", clear_on_submit=True):
        auteur = st.text_input("Auteur", value="Rémi")
        obs_text = st.text_area("Observation / Note météo")
        submitted = st.form_submit_button("Enregistrer l'observation")

        if submitted and obs_text:
            if sheet_j:
                try:
                    horodatage = current_timestamp.strftime("%Y-%m-%d %H:%M")
                    sheet_j.append_row([horodatage, auteur, obs_text])
                    st.success("Observation ajoutée au journal de bord !")
                except Exception as e:
                    st.error(f"Erreur lors de la sauvegarde : {e}")
            else:
                st.error("Impossible de se connecter à la feuille du journal.")

    if sheet_j:
        try:
            entries = sheet_j.get_all_records()
            if entries:
                df_j = pd.DataFrame(entries)
                st.markdown("### 📋 Historique des Observations")
                st.dataframe(df_j, use_container_width=True)
        except Exception:
            pass

with tab8:
    st.subheader("🌐 Radar Météo & Pluie en direct (Windy)")
    st.caption("Localisation centrée sur Habère-Poche / Vallée Verte")

    windy_html = """
    <iframe width="100%" height="450" src="https://embed.windy.com/embed2.html?lat=46.246&lon=6.472&detailLat=46.246&detailLon=6.472&width=650&height=450&zoom=10&level=surface&overlay=radar&product=radar&menu=&message=&marker=&calendar=now&pressure=&type=map&location=coordinates&detail=&metricWind=default&metricTemp=default&radarRange=-1" frameborder="0"></iframe>
    """
    st.components.v1.html(windy_html, height=470)
