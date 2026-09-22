margin=dict(l=10, r=10, t=40, b=10),
            xaxis_title="Date",
            yaxis_title="Précipitations (mm)",
            template="plotly_white",
        )
        st.plotly_chart(fig_rain, use_container_width=True)
    else:
        st.info("Aucune donnée de pluviométrie enregistrée pour le moment.")

with tab4:
    st.subheader("☁️ Plancher Nuageux & Altitude des Nuages (LCL)")

    if base_sol is not None and altitude_mer is not None:
        c_n1, c_n2 = st.columns(2)
        c_n1.metric(
            "Base des nuages (par rapport au sol)",
            f"{base_sol} m",
            help="Calculé via la formule du niveau de condensation par élévation (LCL).",
        )
        c_n2.metric(
            "Altitude de la base (niveau de la mer)",
            f"{altitude_mer} m",
            help="Altitude de la station (900m) + hauteur du plancher nuageux.",
        )

        st.markdown("---")
        st.write("### 🏔️ Repères orographiques locaux")
        st.write(
            f"- **Village d'Habère-Poche :** 900 m\n"
            f"- **Col de Terramont :** ~1 100 m\n"
            f"- **Mont Hirmentaz :** 1 607 m\n"
        )

        if altitude_mer < 900:
            st.warning(
                "🌫️ **Brouillard / Nuages bas :** La condensation s'effectue"
                " directement au niveau du sol ou en dessous de la station."
            )
        elif 900 <= altitude_mer <= 1607:
            st.info(
                f"☁️ **Nuages accrochant les relief :** Les cumulus se forment"
                f" à **{altitude_mer} m**, sous le sommet du mont Hirmentaz."
            )
        else:
            st.success(
                f"🌤️ **Reliefs dégagés :** Les nuages sont situés au-dessus des"
                f" sommets environnants (**{altitude_mer} m**)."
            )
    else:
        st.warning(
            "Données de température ou d'humidité insuffisantes pour calculer"
            " la base des nuages."
        )

with tab5:
    st.subheader("📈 Historique & Tendances Barométriques")

    if not df_hist.empty and "timestamp" in df_hist.columns:
        df_hist_clean = df_hist.dropna(subset=["timestamp"]).copy()

        fig_temp = px.line(
            df_hist_clean,
            x="timestamp",
            y=["temperature", "ressenti"],
            title="Évolution de la Température et du Ressenti (°C)",
            labels={"value": "Température (°C)", "timestamp": "Horodatage"},
        )
        fig_temp.update_layout(
            height=280,
            margin=dict(l=10, r=10, t=40, b=10),
            template="plotly_white",
        )
        st.plotly_chart(fig_temp, use_container_width=True)

        fig_press = px.line(
            df_hist_clean,
            x="timestamp",
            y="pression",
            title="Évolution de la Pression Relative (hPa)",
            labels={"pression": "Pression (hPa)", "timestamp": "Horodatage"},
        )
        fig_press.update_layout(
            height=280,
            margin=dict(l=10, r=10, t=40, b=10),
            template="plotly_white",
        )
        st.plotly_chart(fig_press, use_container_width=True)
    else:
        st.info("Aucun historique disponible dans la feuille Google Sheet.")

with tab6:
    st.subheader("💡 Prévisions & Analyse Météorologique")

    col_fitz, col_rules = st.columns(2)

    fitz_res = get_fitzroy_forecast(delta_press)
    with col_fitz:
        with st.container(border=True):
            st.write("### 📜 Baromètre de FitzRoy")
            st.markdown(f"## {fitz_res['icon']} {fitz_res['status']}")
            st.write(f"**Tendance :** {fitz_res['desc']}")
            st.write(f"**Tendance 3h :** {tendance_libelle}")

    rules_res = get_combined_rules_forecast(
        temp, humidity, pressure, delta_press, wind_dir
    )
    with col_rules:
        with st.container(border=True):
            st.write("### 🧭 Analyse Régionale Avancée")
            if rules_res["level"] == "warning":
                st.warning(rules_res["summary"])
            elif rules_res["level"] == "success":
                st.success(rules_res["summary"])
            else:
                st.info(rules_res["summary"])
            st.write(f"**Indice de confiance :** {indice_confiance}")

    st.markdown("---")
    st.write("### 🏔️ Risques & Paramètres de Montagne")
    r1, r2, r3 = st.columns(3)
    r1.metric("Risque de gel", risque_gel)
    r2.metric(
        "Point de rosée",
        f"{point_rosee} °C" if point_rosee is not None else "N/A",
    )
    r3.metric(
        "Évapotranspiration (ETP estimée)",
        f"{etp_val} mm/j",
        help="Estimation simplifiée basée sur la formule de Hargreaves.",
    )

with tab7:
    st.subheader("📓 Journal de Bord & Normales Climatologiques")

    tab_j1, tab_j2 = st.tabs(["Climatologie Locale", "Notes & Observations"])

    with tab_j1:
        mois_actuel = current_timestamp.month
        norm = obtenir_normales_saison(mois_actuel)

        st.write(f"### 🌡️ Normales pour le mois n°{mois_actuel}")
        st.write(f"**Incertitude / Description :** {norm['desc']}")

        cn1, cn2 = st.columns(2)
        cn1.metric("Tn Normale (Minimale)", f"{norm['t_min']} °C")
        cn2.metric("Tx Normale (Maximale)", f"{norm['t_max']} °C")

    with tab_j2:
        sheet_j = connecter_feuille_journal()
        if sheet_j:
            with st.form("form_observation", clear_on_submit=True):
                auteur = st.text_input("Auteur", value="Rémi")
                obs = st.text_area("Observation météo / jardin / flore")
                soumis = st.form_submit_button("Enregistrer l'observation")

                if soumis and obs:
                    try:
                        sheet_j.append_row(
                            [
                                current_timestamp.strftime("%Y-%m-%d %H:%M"),
                                auteur,
                                obs,
                            ]
                        )
                        st.success("Observation enregistrée avec succès !")
                    except Exception as e:
                        st.error(f"Erreur lors de l'enregistrement : {e}")

            st.markdown("---")
            st.write("### 📜 Dernières observations")
            try:
                data_j = sheet_j.get_all_records()
                if data_j:
                    df_j = pd.DataFrame(data_j)
                    st.dataframe(
                        df_j.iloc[::-1], use_container_width=True, height=250
                    )
                else:
                    st.info("Aucune observation consignée pour l'instant.")
            except Exception:
                st.info("Chargement du journal indisponible.")

with tab8:
    st.subheader("🌐 Radar Météo & Animation Pluie (Windy)")
    st.write(
        "Visuel dynamique centré sur Habère-Poche et la Vallée Verte."
    )

    windy_iframe = """
    <iframe width="100%" height="500"
        src="https://embed.windy.com/embed2.html?lat=46.248&lon=6.473&detailLat=46.248&detailLon=6.473&width=650&height=500&zoom=10&level=surface&overlay=radar&product=radar&menu=&message=true&marker=true&calendar=now&pressure=&type=map&location=coordinates&detail=&metricWind=default&metricTemp=default&radarRange=-1"
        frameborder="0">
    </iframe>
    """
    st.components.v1.html(windy_iframe, height=520)
