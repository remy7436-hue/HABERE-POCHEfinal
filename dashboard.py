import streamlit as st
import requests
import pandas as pd
import numpy as np
import plotly.express as px
import plotly.graph_objects as go
from datetime import datetime
import os
import base64
import time
import pytz
import gspread
from google.oauth2.service_account import Credentials

# 1. Configuration de la page
st.set_page_config(
    page_title="Météo Habère-Poche",
    page_icon="🏔️",
    layout="wide"
)

# 2. Récupération des secrets (Ecowitt + Google Sheets)
ECOWITT_API_KEY = st.secrets.get("ECOWITT_API_KEY", "")
ECOWITT_APP_KEY = st.secrets.get("ECOWITT_APP_KEY", "")
GW3000_MAC = st.secrets.get("GW3000_MAC", "")

SHEET_NAME = "Historique_Meteo_Habere_Poche"


# 3. Connexion au Google Sheet (Mise en cache & gestion robuste Base64 / PEM)
@st.cache_resource
def connecter_google_sheet():
    scope = [
        "https://www.googleapis.com/auth/spreadsheets",
        "https://www.googleapis.com/auth/drive"
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


def charger_historique_gsheet():
    df_vide = pd.DataFrame(columns=[
        "timestamp", "heure", "temperature", "ressenti",
        "humidite", "pression", "pression_abs", "vent",
        "rafale", "direction", "pluie"
    ])
    try:
        sheet = connecter_google_sheet()
        data = sheet.get_all_records()
        if data:
            df = pd.DataFrame(data)
            if not df.empty and "timestamp" in df.columns:
                df["timestamp"] = pd.to_datetime(df["timestamp"], errors="coerce")
                df = df.dropna(subset=["timestamp"])
                if not df.empty:
                    cols_num = ["temperature", "ressenti", "humidite", "pression", "pression_abs", "vent", "rafale", "direction", "pluie"]
                    for col in cols_num:
                        if col in df.columns:
                            df[col] = pd.to_numeric(df[col], errors="coerce")

                    df = df.sort_values("timestamp").reset_index(drop=True)
                    if "pluie" not in df.columns:
                        df["pluie"] = 0.0
                    return df
    except Exception:
        pass

    return df_vide


def sauvegarder_mesure_gsheet(timestamp, heure, temp, ressenti, humidite, pression, pression_abs, vent, rafale, direction, pluie):
    df = charger_historique_gsheet()

    timestamp_propre = timestamp.replace(microsecond=0)
    actuel_temps = timestamp_propre.strftime("%Y-%m-%d %H:%M")

    if not df.empty and "timestamp" in df.columns:
        dernier_temps = pd.to_datetime(df.iloc[-1]["timestamp"]).strftime("%Y-%m-%d %H:%M") if pd.notnull(df.iloc[-1]["timestamp"]) else ""
        if dernier_temps == actuel_temps:
            return df

    nouvelle_ligne = [
        timestamp_propre.strftime("%Y-%m-%d %H:%M:%S"),
        heure, temp, ressenti, humidite, pression,
        pression_abs, vent, rafale, direction, pluie
    ]

    try:
        sheet = connecter_google_sheet()
        sheet.append_row(nouvelle_ligne)
    except Exception:
        pass

    nouvelle_df = pd.DataFrame([{
        "timestamp": timestamp_propre, "heure": heure, "temperature": temp,
        "ressenti": ressenti, "humidite": humidite, "pression": pression,
        "pression_abs": pression_abs, "vent": vent, "rafale": rafale,
        "direction": direction, "pluie": pluie
    }])
    df = pd.concat([df, nouvelle_df], ignore_index=True)
    return df


# 4. Fonctions utilitaires & conversion d'unités Ecowitt
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
    if deg is None or pd.isna(deg): return "N/A"
    try:
        dirs = ["N", "NNE", "NE", "ENE", "E", "ESE", "SE", "SSE", "S", "SSO", "SO", "OSO", "O", "ONO", "NO", "NNO"]
        return dirs[int((float(deg) + 11.25) / 22.5) % 16]
    except Exception: return "N/A"

def calculer_base_cumulus(temp, humidite, altitude_station=900):
    if temp is None or humidite is None: return None, None
    try:
        t, rh = float(temp), float(humidite)
        alpha = ((17.27 * t) / (237.7 + t)) + np.log(rh / 100.0)
        dew_point = (237.7 * alpha) / (17.27 - alpha)
        base_sol = (t - dew_point) * 125.0
        return round(base_sol), round(base_sol + altitude_station)
    except Exception: return None, None

def calculer_ressenti(temp, wind_speed_kmh, humidite):
    if temp is None: return None, "Indisponible"
    if temp <= 10.0 and wind_speed_kmh and wind_speed_kmh > 4.8:
        wc = 13.12 + 0.6215 * temp - 11.37 * (wind_speed_kmh ** 0.16) + 0.3965 * temp * (wind_speed_kmh ** 0.16)
        return round(wc, 1), "Windchill (Vent)"
    elif temp >= 20.0 and humidite:
        alpha = ((17.27 * temp) / (237.7 + temp)) + np.log(humidite / 100.0)
        dew_point = (237.7 * alpha) / (17.27 - alpha)
        e = 6.11 * np.exp(5417.7530 * ((1 / 273.16) - (1 / (273.15 + dew_point))))
        return round(temp + (5/9) * (e - 10), 1), "Humidex (Moiteur)"
    return temp, "Standard"

def analyser_risques_montagne(temp, humidite, pression):
    if temp is None or humidite is None: return "Indisponible", 0.1, 0.0
    alpha = ((17.27 * temp) / (237.7 + temp)) + np.log(humidite / 100.0)
    dew_point = (237.7 * alpha) / (17.27 - alpha)
    risque = "🚨 Risque de gel imminent !" if temp <= 2.0 else ("⚠️ Risque de gelée blanche" if temp <= 5.0 and dew_point <= 2.0 else "✅ Pas de risque de gel")
    etp = max(0.1, round(0.0023 * (temp + 17.8) * (100 - humidite)**0.5 * 5, 2))
    return risque, etp, round(dew_point, 1)

def prevision_zambretti(p, tendance):
    if p is None: return "Données barométriques insuffisantes."
    if tendance > 0.1:
        return "☀️ Temps beau et stable (Anticyclone fort)" if p >= 1030 else "🌤️ Beau temps persistant"
    elif tendance < -0.1:
        return "⛈️ Dégradation rapide, pluie ou orages imminents" if p < 1000 else "🌧️ Risque d'averses, temps pluvieux"
    return "☀️ Temps beau, stable et sec" if p >= 1025 else "☁️ Temps changeant, passages nuageux"

def interpreter_vent_local(degres, vitesse):
    temp_deg = float(degres) if degres is not None and not pd.isna(degres) else 0.0
    if degres is None or pd.isna(degres) or vitesse < 3: return "Calme / Vent variable", "💤"
    if 315 <= temp_deg or temp_deg < 45: return "Bise / Vent de Nord : Assèchement, fraîcheur.", "🌬️"
    elif 45 <= temp_deg < 135: return "Vent d'Est : Flux continental stable.", "🌤️"
    elif 135 <= temp_deg < 225: return "Vent du Sud / Sud-Ouest : Doux, annonciateur de pluie/orages.", "⛈️"
    return "Vent d'Ouest / Nord-Ouest : Traîne, averses.", "🌧️"


# 5. Récupération API Ecowitt
def fetch_ecowitt_data(app_key, api_key, mac):
    url = "https://api.ecowitt.net/api/v3/device/real_time"
    params = {"application_key": app_key, "api_key": api_key, "mac": mac, "call_by": "all", "unit": "1"}
    try:
        res = requests.get(url, params=params, timeout=8)
        if res.status_code == 200: return res.json()
    except Exception: pass
    return None


# Sidebar
with st.sidebar:
    st.header("⚙️ Station Météo — Cloud")
    st.write("**Altitude :** 900 m (Habère-Poche)")
    if st.button("🔄 Forcer la synchro & Actualiser"):
        st.rerun()

st.title("🏔️ Station Météo — Habère-Poche")

raw_data = fetch_ecowitt_data(ECOWITT_APP_KEY, ECOWITT_API_KEY, GW3000_MAC)
if not raw_data or raw_data.get("code") != 0:
    st.error("Impossible de récupérer les données depuis l'API Ecowitt. Vérifie tes clés et ton MAC dans les Secrets.")
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
risque_gel, etp_val, point_rosee = analyser_risques_montagne(temp, humidity, pressure)

timezone = pytz.timezone("Europe/Paris")
current_timestamp = datetime.now(timezone)
current_time_str = current_timestamp.strftime("%H:%M:%S")

df_hist = sauvegarder_mesure_gsheet(
    current_timestamp, current_time_str, temp, temp_ressentie,
    humidity, pressure, pressure_abs, wind_speed, wind_gust, wind_dir, rain_day
)

if not df_hist.empty and "timestamp" in df_hist.columns:
    df_hist["timestamp"] = pd.to_datetime(df_hist["timestamp"], errors="coerce")

delta_temp = round(float(df_hist.iloc[-1]["temperature"]) - float(df_hist.iloc[-2]["temperature"]), 1) if len(df_hist) >= 2 else 0.0
delta_hum = round(float(df_hist.iloc[-1]["humidite"]) - float(df_hist.iloc[-2]["humidite"]), 1) if len(df_hist) >= 2 else 0.0
delta_press = round(float(df_hist.iloc[-1]["pression"]) - float(df_hist.iloc[-2]["pression"]), 2) if len(df_hist) >= 2 else 0.0

max_temp, min_temp, max_temp_time, min_temp_time = "--", "--", "", ""
max_wind, max_gust = 0.0, 0.0
if not df_hist.empty and "timestamp" in df_hist.columns:
    df_today = df_hist[df_hist["timestamp"].dt.strftime("%Y-%m-%d") == current_timestamp.strftime("%Y-%m-%d")]
    if not df_today.empty:
        df_today["temperature"] = pd.to_numeric(df_today["temperature"], errors="coerce")
        df_today_clean = df_today[(df_today["temperature"] >= -30) & (df_today["temperature"] <= 50)]
        if not df_today_clean.empty:
            max_t, min_t = df_today_clean.loc[df_today_clean["temperature"].idxmax()], df_today_clean.loc[df_today_clean["temperature"].idxmin()]
            max_temp, max_temp_time = max_t["temperature"], max_t["heure"]
            min_temp, min_temp_time = min_t["temperature"], min_t["heure"]
        max_wind, max_gust = pd.to_numeric(df_today["vent"], errors="coerce").max(), pd.to_numeric(df_today["rafale"], errors="coerce").max()

tendance_baro = round(float(df_hist.iloc[-1]["pression"]) - float(df_hist.iloc[0]["pression"]), 2) if len(df_hist) >= 2 else 0.0
prevision_texte = prevision_zambretti(pressure, tendance_baro)


# 6. Onglets de l'application
tab1, tab2, tab3, tab4, tab5, tab6 = st.tabs([
    "📊 Temps Réel & Extrêmes", "🧭 Rose des Vents", "🌧️ Pluviométrie",
    "☁️ Plancher Nuageux", "📈 Historique & Tendances", "💡 Prévisions & Analyse"
])

with tab1:
    st.subheader("📡 Conditions Actuelles (Flux Ecowitt Cloud)")
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Température", f"{temp} °C", delta=f"{delta_temp:+.1f} °C")
    c2.metric("Humidité", f"{humidity} %", delta=f"{delta_hum:+.1f} %")
    c3.metric("Pression relative", f"{pressure} hPa", delta=f"{delta_press:+.2f} hPa")
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
    e1, e2, e3, e4 = st.columns(4)
    e1.metric("Max Chaleur (Tx)", f"{max_temp} °C" if max_temp != "--" else "--", f"à {max_temp_time}")
    e2.metric("Min Fraîcheur (Tn)", f"{min_temp} °C" if min_temp != "--" else "--", f"à {min_temp_time}")
    e3.metric("Vent max", f"{max_wind} km/h")
    e4.metric("Rafale max", f"{max_gust} km/h")
    st.caption(f"Synchro cloud : **{current_time_str}** | Lignes dans Google Sheet : **{len(df_hist)}**")

with tab2:
    st.subheader("🧭 Rose des Vents (Google Sheet)")
    if not df_hist.empty and "direction" in df_hist.columns:
        df_rose = df_hist.dropna(subset=["direction", "vent"]).copy()
        df_rose["vent"] = pd.to_numeric(df_rose["vent"], errors="coerce")
        df_rose["direction"] = pd.to_numeric(df_rose["direction"], errors="coerce")
        df_rose = df_rose.dropna(subset=["direction", "vent"])

        if not df_rose.empty:
            bins = [-11.25 + i * 22.5 for i in range(17)]
            labels_deg = [i * 22.5 for i in range(16)]
            noms_secteurs = ["N", "NNE", "NE", "ENE", "E", "ESE", "SE", "SSE", "S", "SSO", "SO", "OSO", "O", "ONO", "NO", "NNO"]

            df_rose["bin_deg"] = pd.cut(df_rose["direction"] % 360, bins=bins, labels=labels_deg, include_lowest=True)
            df_rose["bin_deg"] = df_rose["bin_deg"].astype(float)

            df_grp = df_rose.groupby("bin_deg").agg(
                count=("vent", "count"),
                mean=("vent", "mean")
            ).reindex(labels_deg, fill_value=0).reset_index()

            df_grp["nom"] = noms_secteurs

            fig_rose = go.Figure(go.Barpolar(
                r=df_grp["count"],
                theta=df_grp["bin_deg"],
                width=22.5,
                marker=dict(
                    color=df_grp["mean"],
                    colorscale="Blues",
                    showscale=True,
                    colorbar=dict(title="Vent moyen (km/h)")
                ),
                text=df_grp["nom"],
                hoverinfo="text+r"
            ))

            fig_rose.update_layout(
                polar=dict(
                    angularaxis=dict(
                        tickvals=labels_deg,
                        ticktext=noms_secteurs,
                        direction="clockwise",
                        rotation=90
                    )
                ),
                height=500
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
        c_p1.metric("Cumul récent", f"{df_journalier.iloc[-1]['pluie'] if not df_journalier.empty else 0.0} mm")
        st.plotly_chart(px.bar(df_journalier, x="date_seule", y="pluie", title="Cumul journalier"), use_container_width=True)
    else: st.info("En attente de données de pluie...")

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
                fig_pano.add_layout_image(dict(
                    source=f"data:image/jpeg;base64,{base64.b64encode(f.read()).decode()}",
                    xref="x", yref="y", x=0, y=3000, sizex=10, sizey=2600, sizing="stretch", opacity=0.85, layer="below"
                ))
        fig_pano.add_hline(y=altitude_mer, line_dash="dash", line_color="red", annotation_text=f"☁️ Nuages ({altitude_mer} m)")
        fig_pano.update_layout(xaxis=dict(visible=False, range=[-0.5, 9.5]), yaxis=dict(range=[400, 3000]), height=500)
        st.plotly_chart(fig_pano, use_container_width=True)
    else: st.info("Calcul du plancher nuageux indisponible.")

with tab5:
    st.subheader("📈 Historique & Tendances Lissées")
    if not df_hist.empty:
        df_plot = df_hist.copy()

        df_plot["temperature"] = pd.to_numeric(df_plot["temperature"], errors="coerce")
        df_plot["ressenti"] = pd.to_numeric(df_plot["ressenti"], errors="coerce")
        df_plot["humidite"] = pd.to_numeric(df_plot["humidite"], errors="coerce")
        df_plot["pression"] = pd.to_numeric(df_plot["pression"], errors="coerce")
        df_plot["vent"] = pd.to_numeric(df_plot["vent"], errors="coerce")
        df_plot["direction"] = pd.to_numeric(df_plot["direction"], errors="coerce")

        df_plot.loc[(df_plot["temperature"] < -30) | (df_plot["temperature"] > 50), "temperature"] = np.nan
        df_plot.loc[(df_plot["ressenti"] < -40) | (df_plot["ressenti"] > 60), "ressenti"] = np.nan
        df_plot.loc[(df_plot["pression"] < 900) | (df_plot["pression"] > 1100), "pression"] = np.nan

        # Graphique Température & Ressenti robuste (Go.Figure)
        fig_temp = go.Figure()
        fig_temp.add_trace(go.Scatter(
            x=df_plot["timestamp"], y=df_plot["temperature"],
            mode="lines", name="Température (°C)",
            line=dict(shape="spline", color="rgb(31, 119, 180)", width=2)
        ))
        fig_temp.add_trace(go.Scatter(
            x=df_plot["timestamp"], y=df_plot["ressenti"],
            mode="lines", name="Ressenti (°C)",
            line=dict(shape="spline", color="rgb(174, 199, 232)", width=2, dash="dash")
        ))
        fig_temp.update_layout(title="Températures et Ressenti (°C)", xaxis_title="Temps", yaxis_title="°C", height=400)
        st.plotly_chart(fig_temp, use_container_width=True)

        # Graphique Humidité (Spline)
        fig_hum = px.line(df_plot, x="timestamp", y="humidite", title="Humidité relative (%)")
        fig_hum.update_traces(line_shape="spline", line_color="teal")
        st.plotly_chart(fig_hum, use_container_width=True)

        # Graphique Pression atmosphérique (Spline)
        fig_press = px.line(df_plot, x="timestamp", y="pression", title="Pression atmosphérique (hPa)")
        fig_press.update_traces(line_shape="spline", line_color="rebeccapurple")
        st.plotly_chart(fig_press, use_container_width=True)

        # Graphique Direction du vent
        fig_dir = px.scatter(df_plot, x="timestamp", y="direction", title="Direction du vent au fil du temps (en degrés)", labels={"direction": "Direction (°)"})
        fig_dir.update_traces(marker=dict(size=6, color="orange"))
        fig_dir.update_layout(yaxis=dict(range=[0, 360], tickvals=[0, 90, 180, 270, 360], ticktext=["N (0°)", "E (90°)", "S (180°)", "O (270°)", "N (360°)"]))
        st.plotly_chart(fig_dir, use_container_width=True)
    else:
        st.info("Historique vide pour le moment.")

with tab6:
    st.subheader("🔮 Prévisions & Analyse de Moyenne Montagne")
    if pressure:
        st.success(f"### Tendance : **{prevision_texte}**")
    st.markdown("---")
    g1, g2, g3 = st.columns(3)
    g1.metric("Risque gel", risque_gel)
    g2.metric("Évapotranspiration (ETP)", f"{etp_val} mm/j")
    g3.metric("Point de rosée", f"{point_rosee} °C")

    st.markdown("---")
    if wind_dir is not None:
        interp, emoji = interpreter_vent_local(wind_dir, wind_speed)
        st.markdown(f"### {emoji} {interp}")

# Rafraîchissement automatique toutes les 5 minutes
time.sleep(300)
st.rerun()
