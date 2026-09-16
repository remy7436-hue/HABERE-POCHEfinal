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

# 2. Application de styles CSS personnalisés pour un rendu "Centre de Contrôle" moderne
st.markdown("""
    <style>
    .main {
        background-color: #f8fafc;
    }
    .stMetric {
        background-color: #ffffff;
        padding: 16px;
        border-radius: 12px;
        box-shadow: 0 4px 6px -1px rgba(0,0,0,0.05), 0 2px 4px -1px rgba(0,0,0,0.03);
        border: 1px solid #e2e8f0;
        transition: transform 0.2s ease;
    }
    .stMetric:hover {
        transform: translateY(-2px);
        box-shadow: 0 10px 15px -3px rgba(0,0,0,0.05);
    }
    h1, h2, h3 {
        color: #1e293b;
        font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
    }
    </style>
""", unsafe_allow_html=True)

# 3. Récupération des secrets (Ecowitt + Google Sheets)
ECOWITT_API_KEY = st.secrets.get("ECOWITT_API_KEY", "")
ECOWITT_APP_KEY = st.secrets.get("ECOWITT_APP_KEY", "")
GW3000_MAC = st.secrets.get("GW3000_MAC", "")

SHEET_NAME = "Historique_Meteo_Habere_Poche"
SHEET_JOURNAL = "Journal_Observations"


# 4. Connexion au Google Sheet (Mise en cache & gestion robuste Base64 / PEM)
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
            sheet_j = client.open(SHEET_NAME).add_worksheet(title=SHEET_JOURNAL, rows=100, cols=3)
            sheet_j.append_row(["Date", "Auteur", "Observation"])
        return sheet_j
    except Exception:
        return None


def nettoyer_timestamp_robuste(valeur_brute):
    """Extrait un format de date propre YYYY-MM-DD HH:MM:SS même en cas de concaténation parasite."""
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
    df_vide = pd.DataFrame(columns=[
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
    ])
    try:
        sheet = connecter_google_sheet()
        data = sheet.get_all_records()
        if data:
            df = pd.DataFrame(data)
            if not df.empty and "timestamp" in df.columns:
                df["timestamp"] = df["timestamp"].apply(nettoyer_timestamp_robuste)
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

    nouvelle_df = pd.DataFrame([{
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
    }])
    df = pd.concat([df, nouvelle_df], ignore_index=True)
    return df


# 5. Fonctions utilitaires & conversion d'unités Ecowitt
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


def analyser_risques_montagne(temp, humidite, pression):
    if temp is None or humidite is None:
        return "Indisponible", 0.1, 0.0
    alpha = ((17.27 * temp) / (237.7 + temp)) + np.log(humidite / 100.0)
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
    """Calcule la tendance barométrique sur 3h glissantes pour lisser la volatilité."""
    if df_hist is None or len(df_hist) < 2 or "timestamp" not in df_hist.columns:
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
            "☀️ Temps beau, stable et sec" if pression_actuelle >= 1025 else "☁️ Temps changeant",
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
            "🌧️ Dégradation marquée confirmée, approche d'une perturbation active."
            if pression_actuelle < 1015
            else "⚠️ Baisse rapide de pression, changement de temps imminent."
        )
        indice_confiance = "Élevée (Passage perturbé)"
    else:
        if pression_actuelle >= 1020:
            prevision = "☀️ Temps stable, sec et bien établi sur le secteur de la Vallée Verte."
            indice_confiance = "Moyenne à Haute"
        elif pression_actuelle <= 1005:
            prevision = "☁️ Conditions dépressionnaires persistantes, passages nuageux fréquents."
            indice_confiance = "Moyenne"
        else:
            prevision = "☁️ Temps variable et de saison, alternance d'éclaircies."
            indice_confiance = "Modérée (Variable)"

    return tendance_3h, libelle_tendance, prevision, indice_confiance


def obtenir_normales_saison(mois):
    """Normales climatiques approximatives pour Habère-Poche (900m)"""
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
    return normales.get(mois, {"t_min": 5.0, "t_max": 15.0, "desc": "Normales de saison standard."})


def interpreter_vent_local(degres, vitesse):
    temp_deg = (
        float(degres) if degres is not None and not pd.isna(degres) else 0.0
    )
    if degres is None or pd.isna(degres) or vitesse < 3:
        return "Calme / Vent variable (Stabilité locale)", "💤"
    if 315 <= temp_deg or temp_deg < 45:
        return "Bise / Vent de Nord : Assèchement, fraîcheur montagnarde.", "🌬️"
    elif 45 <= temp_deg < 135:
        return "Vent d'Est : Flux continental stable.", "🌤️"
    elif 135 <= temp_deg < 225:
        return "Vent du Sud / Sud-Ouest : Doux, flux perturbé annonciateur de précipitations.", "⛈️"
    return "Vent d'Ouest / Nord-Ouest : Régime de traîne, averses possibles.", "🌧️"


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
    lissage_active = st.checkbox("Lissage vectoriel 3h (Rose des Vents)", value=True, help="Lisse les fluctuations rapides du vent.")

    if st.button("🔄 Forcer la synchro & Actualiser"):
        st.rerun()

st.title("🏔️ Station Météo — Habère-Poche")

raw_data = fetch_ecowitt_data(ECOWITT_APP_KEY, ECOWITT_API_KEY, GW3000_MAC)
if not raw_data or raw_data.get("code") != 0:
    st.error(
        "Impossible de récupérer les données depuis l'API Ecowitt. Vérifie tes"
        " clés et ton MAC dans les Secrets."
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

base_sol, altitude_mer = calculer_base_cumulus(temp, humidity, 900)
temp_ressentie, mode_ressenti = calculer_ressenti(temp, wind_speed, humidity)
risque_gel, etp_val, point_rosee = analyser_risques_montagne(
    temp, humidity, pressure
)

try:
    timezone = zoneinfo.ZoneInfo("Europe/Paris")
except Exception:
    timezone = timezone(timedelta(hours=2))

current_timestamp = datetime.now(timezone)
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

max_temp, min_temp, max_temp_time, min_temp_time = "--", "--", "", ""
max_wind, max_gust = 0.0, 0.0
if not df_hist.empty and "timestamp" in df_hist.columns:
    df_valid_time = df_hist.dropna(subset=["timestamp"])
    if not df_valid_time.empty:
        df_today = df_valid_time[
            df_valid_time["timestamp"].dt.strftime("%Y-%m-%d")
            == current_timestamp.strftime("%Y-%m-%d")
        ]
        if not df_today.empty:
            df_today["temperature"] = pd.to_numeric(
                df_today["temperature"], errors="coerce"
            )
            df_today_clean = df_today[
                (df_today["temperature"] >= -30) & (df_today["temperature"] <= 50)
            ]
            if not df_today_clean.empty:
                max_t, min_t = (
                    df_today_clean.loc[df_today_clean["temperature"].idxmax()],
                    df_today_clean.loc[df_today_clean["temperature"].idxmin()],
                )
                max_temp, max_temp_time = max_t["temperature"], max_t["heure"]
                min_temp, min_temp_time = min_t["temperature"], min_t["heure"]
            max_wind, max_gust = pd.to_numeric(
                df_today["vent"], errors="coerce"
            ).max(), pd.to_numeric(df_today["rafale"], errors="coerce").max()

tendance_val, tendance_libelle, prevision_texte, indice_confiance = (
    calculer_tendance_et_prevision_robuste(df_hist, pressure)
)


# 7. Onglets de l'application
tab1, tab2, tab3, tab4, tab5, tab6, tab7 = st.tabs([
    "📊 Temps Réel & Extrêmes",
    "🧭 Rose des Vents",
    "🌧️ Pluviométrie",
    "☁️ Plancher Nuageux",
    "📈 Historique & Tendances",
    "💡 Prévisions & Analyse",
    "📓 Journal de Bord & Climat"
])

with tab1:
    st.subheader("📡 Conditions Actuelles (Flux Ecowitt Cloud)")

    with st.container(border=True):
        c1, c2, c3, c4 = st.columns(4)
        c1.metric("Température", f"{temp} °C", delta=f"{delta_temp:+.1f} °C")
        c2.metric("Humidité", f"{humidity} %", delta=f"{delta_hum:+.1f} %")
        c3.metric(
            "Pression relative", f"{pressure} hPa", delta=f"{delta_press:+.2f} hPa"
        )
        c4.metric("Pression absolue", f"{pressure_abs} hPa")

        st.markdown("---")
        c5, c6, c7, c8 = st.columns(4)
        c5.metric("Ressenti", f"{temp_ressentie} °C", help=mode_ressenti)
        c6.metric("Vent moyen", f"{wind_speed} km/h")
        c7.metric("Rafale", f"{wind_gust} km/h")
        c8.metric("Direction", f"{degres_vers_cardinal(wind_dir)} ({int(wind_dir)}°)")

        st.markdown("---")
        c5_b, _ = st.columns(2)
        c5_b.metric("Pluie du jour", f"{rain_day} mm")

    st.markdown("### 🏆 Extrêmes du jour")
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
        f"Synchro cloud : **{current_time_str}** | Lignes dans Google Sheet :"
        f" **{len(df_hist)}**"
    )

with tab2:
    st.subheader("🧭 Rose des Vents Améliorée (Google Sheet)")
    if not df_hist.empty and "direction" in df_hist.columns:
        df_rose = df_hist.dropna(subset=["direction", "vent"]).copy()
        df_rose["vent"] = pd.to_numeric(df_rose["vent"], errors="coerce")
        df_rose["direction"] = pd.to_numeric(df_rose["direction"], errors="coerce")
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
                df_rose = df_rose.reset_index().dropna(subset=["direction", "vent"])

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

            titre_rose = f"Rose des Vents Améliorée (Vents calmes : {calm_percentage:.1f}%"
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
        else:
            st.info("Accumulation des vents en cours...")
    else:
        st.info("En attente de données...")

with tab3:
    st.subheader("🌧️ Suivi de la Pluviométrie")
    if not df_hist.empty and "pluie" in df_hist.columns:
        df_rain = df_hist.copy()
        df_rain["pluie"] = pd.to_numeric(df_rain["pluie"], errors="coerce")
        df_rain["date_seule"] = df_rain["timestamp"].dt.date
        df_journalier = df_rain.groupby("date_seule")["pluie"].max().reset_index()

        c_p1, _ = st.columns(2)
        c_p1.metric(
            "Cumul récent",
            f"{df_journalier.iloc[-1]['pluie'] if not df_journalier.empty else 0.0}"
            " mm",
        )
        fig_rain = px.bar(
            df_journalier, x="date_seule", y="pluie", title="Cumul journalier"
        )
        fig_rain.update_layout(
            height=300,
            margin=dict(l=10, r=10, t=40, b=10),
            template="plotly_white"
        )
        st.plotly_chart(
            fig_rain,
            use_container_width=True,
        )
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
                fig_pano.add_layout_image(
                    dict(
                        source=f"data:image/jpeg;base64,{base64.b64encode(f.read()).decode()}",
                        xref="x",
                        yref="y",
                        x=0,
                        y=3000,
                        sizex=10,
                        sizey=2600,
                        sizing="stretch",
                        opacity=0.85,
                        layer="below",
                    )
                )
        fig_pano.add_hline(
            y=altitude_mer,
            line_dash="dash",
            line_color="red",
            annotation_text=f"☁️ Nuages ({altitude_mer} m)",
        )
        fig_pano.update_layout(
            xaxis=dict(visible=False, range=[-0.5, 9.5]),
            yaxis=dict(range=[400, 3000]),
            height=320,
            margin=dict(l=10, r=10, t=40, b=10),
            template="plotly_white"
        )
        st.plotly_chart(fig_pano, use_container_width=True)
    else:
        st.info("Calcul du plancher nuageux indisponible.")

with tab5:
    st.subheader("📈 Historique & Tendances (Altair)")
    if not df_hist.empty:
        df_plot = df_hist.copy()

        df_plot["timestamp"] = pd.to_datetime(df_plot["timestamp"])
        df_plot["temperature"] = pd.to_numeric(df_plot["temperature"], errors="coerce")
        df_plot["ressenti"] = pd.to_numeric(df_plot["ressenti"], errors="coerce")
        df_plot["humidite"] = pd.to_numeric(df_plot["humidite"], errors="coerce")
        df_plot["pression"] = pd.to_numeric(df_plot["pression"], errors="coerce")

        df_plot.loc[
            (df_plot["temperature"] < -30) | (df_plot["temperature"] > 50),
            "temperature",
        ] = np.nan
        df_plot.loc[
            (df_plot["ressenti"] < -40) | (df_plot["ressenti"] > 60), "ressenti"
        ] = np.nan
        df_plot.loc[
            (df_plot["pression"] < 900) | (df_plot["pression"] > 1100), "pression"
        ] = np.nan

        valid_t = df_plot["temperature"].dropna()
        if not valid_t.empty:
            y_min = floor(valid_t.quantile(0.01) - 2)
            y_max = ceil(valid_t.quantile(0.99) + 2)
        else:
            y_min, y_max = 0, 25

        # 1. GRAPHIQUE TEMPÉRATURE & RESSENTI
        df_temp_melt = df_plot.melt(
            id_vars=["timestamp"],
            value_vars=["temperature", "ressenti"],
            var_name="Type",
            value_name="Valeur",
        )
        df_temp_melt["Type"] = df_temp_melt["Type"].replace({
            "temperature": "Température (°C)",
            "ressenti": "Ressenti (°C)",
        })

        chart_temp = (
            alt.Chart(df_temp_melt)
            .mark_line(interpolate="monotone")
            .encode(
                x=alt.X("timestamp:T", title=""),
                y=alt.Y(
                    "Valeur:Q",
                    title="°C",
                    scale=alt.Scale(domain=[y_min, y_max]),
                ),
                color=alt.Color(
                    "Type:N",
                    scale=alt.Scale(
                        domain=["Température (°C)", "Ressenti (°C)"],
                        range=["#0284c7", "#38bdf8"],
                    ),
                    legend=alt.Legend(title=""),
                ),
                strokeDash=alt.condition(
                    alt.datum.Type == "Ressenti (°C)",
                    alt.value([4, 4]),
                    alt.value([0]),
                ),
                defined="isValid(datum.Valeur)"
            )
            .properties(title="Températures et Ressenti (°C)", height=260)
            .interactive()
        )
        st.altair_chart(chart_temp, use_container_width=True)

        # 2. GRAPHIQUE HUMIDITÉ
        chart_hum = (
            alt.Chart(df_plot)
            .mark_area(
                interpolate="monotone",
                color="#0d9488",
                opacity=0.2,
                line=dict(color="#0d9488", width=2),
            )
            .encode(
                x=alt.X("timestamp:T", title=""),
                y=alt.Y(
                    "humidite:Q", title="%", scale=alt.Scale(domain=[0, 100])
                ),
                defined="isValid(datum.humidite)"
            )
            .properties(title="Humidité relative (%)", height=260)
            .interactive()
        )
        st.altair_chart(chart_hum, use_container_width=True)

        valid_p = df_plot["pression"].dropna()
        p_min = floor(valid_p.min() - 2) if not valid_p.empty else 950
        p_max = ceil(valid_p.max() + 2) if not valid_p.empty else 1050

        # 3. GRAPHIQUE PRESSION
        chart_press = (
            alt.Chart(df_plot)
            .mark_line(interpolate="monotone", color="#7c3aed", width=1.5)
            .encode(
                x=alt.X("timestamp:T", title=""),
                y=alt.Y(
                    "pression:Q",
                    title="hPa",
                    scale=alt.Scale(domain=[p_min, p_max], zero=False),
                ),
                defined="isValid(datum.pression)"
            )
            .properties(title="Pression atmosphérique (hPa)", height=260)
            .interactive()
        )
        st.altair_chart(chart_press, use_container_width=True)
    else:
        st.info("Aucun historique disponible dans le Google Sheet.")

with tab6:
    st.subheader("💡 Prévisions & Analyse locale")

    col_p1, col_p2 = st.columns(2)
    with col_p1:
        with st.container(border=True):
            st.markdown("### 🔍 Tendance Barométrique (3h)")
            st.metric("Variation", f"{tendance_val:+.2f} hPa / 3h")
            st.write(f"**Analyse :** {tendance_libelle}")
            st.write(f"**Indice de confiance :** {indice_confiance}")

    with col_p2:
        with st.container(border=True):
            st.markdown("### 🌤️ Prévision Synthétique")
            st.write(prevision_texte)
            st.markdown("---")
            st.write(f"**Point de rosée :** {point_rosee} °C")
            st.write(f"**Risque phytosanitaire / Gel :** {risque_gel}")
            st.write(f"**ETP (Évapotranspiration) :** {etp_val} mm/j")

    st.markdown("### 🌡️ Comparaison aux Normales de Saison (900m)")
    mois_actuel = current_timestamp.month
    normes = obtenir_normales_saison(mois_actuel)

    with st.container(border=True):
        nc1, nc2, nc3 = st.columns(3)
        nc1.metric("Normales T. Min", f"{normes['t_min']} °C")
        nc2.metric("Normales T. Max", f"{normes['t_max']} °C")
        nc3.metric("Climatologie du mois", f"{normes['desc']}")

with tab7:
    st.subheader("📓 Journal de Bord & Climat")

    sheet_j = connecter_feuille_journal()

    with st.form("form_journal"):
        st.write("Ajouter une observation manuelle (ex: observation phénologique, passage d'un front, faune, jardin...)")
        obs_texte = st.text_area("Observation / Remarque")
        auteur_obs = st.text_input("Auteur", value="Rémi")
        submit_obs = st.form_submit_button("Enregistrer dans le Journal")

        if submit_obs and obs_texte.strip():
            date_obs_str = current_timestamp.strftime("%Y-%m-%d %H:%M")
            if sheet_j is not None:
                try:
                    sheet_j.append_row([date_obs_str, auteur_obs, obs_texte])
                    st.success("Observation enregistrée avec succès !")
                except Exception as e:
                    st.error(f"Erreur lors de l'enregistrement : {e}")
            else:
                st.warning("Connexion à la feuille Journal indisponible.")

    st.markdown("### 📜 Historique des Observations")
    if sheet_j is not None:
        try:
            records_j = sheet_j.get_all_records()
            if records_j:
                df_j = pd.DataFrame(records_j)
                st.dataframe(df_j, use_container_width=True)
            else:
                st.info("Aucune observation enregistrée pour le moment.")
        except Exception:
            st.info("Impossible de charger le journal pour l'instant.")
    else:
        st.info("Feuille de journal non connectée.")
