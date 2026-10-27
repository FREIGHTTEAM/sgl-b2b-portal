with tab1:
    st.markdown("Hedef listenizi **Ağırlaştırılmış Boyut Cezası** ile hatasız ayıklayın.")
    col1, col2 = st.columns(2)
    with col1:
        hedef_file = st.file_uploader("1️⃣ Hedef Liste (Excel/CSV)", key="hedef")
    with col2:
        cari_file = st.file_uploader("2️⃣ SGL CARİLER (Excel/CSV)", key="cari")

    if hedef_file and cari_file:
        df_hedef = pd.read_excel(hedef_file) if hedef_file.name.endswith('.xlsx') else pd.read_csv(hedef_file)
        df_cari = pd.read_excel(cari_file) if cari_file.name.endswith('.xlsx') else pd.read_csv(cari_file)
        
        st.markdown("### ⚙️ Eşleştirme Ayarları")
        s_col1, s_col2 = st.columns(2)
        with s_col1:
            hedef_sutun = st.selectbox("Hedef Listedeki Firma Adı Sütunu:", df_hedef.columns)
        with s_col2:
            cari_sutun = st.selectbox("SGL Cari Listesindeki Firma Adı Sütunu:", df_cari.columns)
            
        eslesme_esigi = st.slider("Kabul Edilebilir Minimum Benzerlik Skoru (%)", min_value=50, max_value=100, value=85)
        
        if st.button("🔍 Eşleştirmeyi Başlat"):
            st.info("RapidFuzz ile eşleştirme yapılıyor, lütfen bekleyin...")
            ilerleme = st.progress(0)
            
            hedef_firmalar = df_hedef[hedef_sutun].dropna().astype(str).tolist()
            cari_firmalar = df_cari[cari_sutun].dropna().astype(str).tolist()
            
            sonuclar = []
            toplam = len(hedef_firmalar)
            
            for i, firma in enumerate(hedef_firmalar):
                eslesme = process.extractOne(firma, cari_firmalar, scorer=fuzz.token_sort_ratio)
                
                if eslesme and eslesme[1] >= eslesme_esigi:
                    sonuclar.append({
                        "Firma Adı": firma, 
                        "SGL Cari (Bulunan)": eslesme[0], 
                        "Eşleşme Skoru": round(eslesme[1], 2),
                        "Durum": "✅ Eşleşti"
                    })
                else:
                    sonuclar.append({
                        "Firma Adı": firma, 
                        "SGL Cari (Bulunan)": "-", 
                        "Eşleşme Skoru": round(eslesme[1], 2) if eslesme else 0,
                        "Durum": "❌ Eşleşmedi"
                    })
                
                if i % 20 == 0 or i == toplam - 1:
                    ilerleme.progress((i + 1) / toplam)
                    
            df_sonuc = pd.DataFrame(sonuclar)
            st.success("Eşleştirme Tamamlandı!")
            
            # Verileri ikiye böl
            df_eslesen = df_sonuc[df_sonuc["Durum"] == "✅ Eşleşti"]
            df_eslesmeyen = df_sonuc[df_sonuc["Durum"] == "❌ Eşleşmedi"]
            
            # Eşleşmeyenler için sadece "Firma Adı" sütununu bırak
            df_eslesmeyen_sade = df_eslesmeyen[["Firma Adı"]]
            
            # Ekranda sekmeli gösterim
            tab_e, tab_y = st.tabs([f"✅ Eşleşenler ({len(df_eslesen)})", f"❌ Yeni Potansiyel ({len(df_eslesmeyen_sade)})"])
            with tab_e:
                st.dataframe(df_eslesen)
            with tab_y:
                st.dataframe(df_eslesmeyen_sade)
            
            st.markdown("### 📥 Sonuçları İndir")
            dl_col1, dl_col2 = st.columns(2)
            
            with dl_col1:
                csv_eslesen = df_eslesen.to_csv(index=False).encode('utf-8')
                st.download_button(
                    label="📥 Eşleşen Carileri İndir (Detaylı)",
                    data=csv_eslesen,
                    file_name="Cari_Eslesenler.csv",
                    mime="text/csv",
                )
                
            with dl_col2:
                csv_eslesmeyen = df_eslesmeyen_sade.to_csv(index=False).encode('utf-8')
                st.download_button(
                    label="📥 Eşleşmeyenleri İndir (Sadece Firma Adı)",
                    data=csv_eslesmeyen,
                    file_name="Sifir_Aday_Listesi.csv",
                    mime="text/csv",
                )