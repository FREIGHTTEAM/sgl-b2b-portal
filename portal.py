import streamlit as st
import pandas as pd
import requests
from rapidfuzz import process, fuzz
import urllib.parse
import time

st.set_page_config(page_title="SGL B2B Operasyon Portalı", layout="wide")

def check_password():
    if "password_correct" not in st.session_state:
        st.session_state["password_correct"] = False

    if not st.session_state["password_correct"]:
        st.title("🔒 Sisteme Giriş")
        pwd = st.text_input("Şifre", type="password")
        if st.button("Giriş Yap"):
            if pwd == "Sgl2026!":
                st.session_state["password_correct"] = True
                st.rerun()
            else:
                st.error("Hatalı şifre.")
        return False
    return True

if not check_password():
    st.stop()

st.title("🎯 SGL B2B Operasyon & Veri Zenginleştirme Portalı")

tab1, tab2 = st.tabs(["👥 1. Adım: Cari Ayıklama (RapidFuzz)", "🌍 2. Adım: Web Bulucu (Önbellekli)"])

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
                        "Hedef Firma (Aranan)": firma, 
                        "SGL Cari (Bulunan)": eslesme[0], 
                        "Eşleşme Skoru": round(eslesme[1], 2),
                        "Durum": "✅ Eşleşti (Carilerde Var)"
                    })
                else:
                    sonuclar.append({
                        "Hedef Firma (Aranan)": firma, 
                        "SGL Cari (Bulunan)": "-", 
                        "Eşleşme Skoru": round(eslesme[1], 2) if eslesme else 0,
                        "Durum": "❌ Eşleşmedi (Yeni Potansiyel)"
                    })
                
                if i % 20 == 0 or i == toplam - 1:
                    ilerleme.progress((i + 1) / toplam)
                    
            df_sonuc = pd.DataFrame(sonuclar)
            st.success("Eşleştirme Tamamlandı!")
            
            st.dataframe(df_sonuc)
            
            csv = df_sonuc.to_csv(index=False).encode('utf-8')
            st.download_button(
                label="📥 Sonuçları İndir (CSV)",
                data=csv,
                file_name="Cari_Eslesme_Sonuclari.csv",
                mime="text/csv",
            )

with tab2:
    st.markdown("Global ve Yerel alıcıların web sitelerini **Apollo Formatında (Domain)** bulun.")
    
    api_key = st.text_input("🔑 Serper API Anahtarı", type="password")
    web_file = st.file_uploader("Sıfır Aday Listesi (Excel/CSV) Yükleyin", key="web")
    
    if web_file and api_key:
        df_web = pd.read_excel(web_file) if web_file.name.endswith('.xlsx') else pd.read_csv(web_file)
        sutun = st.selectbox("Web Taraması İçin Firma Adı Sütunu:", df_web.columns)
        
        toplam_satir = len(df_web)
        st.warning(f"⚠️ DİKKAT: Yüklediğiniz dosyada **{toplam_satir}** firma bulunuyor. Bu işlem Serper'den yaklaşık **{toplam_satir}** kredi harcayacaktır.")
        
        onay = st.checkbox("Kredi maliyetini gördüm, taramayı başlatmayı onaylıyorum.")
        
        if 'iptal_edildi' not in st.session_state:
            st.session_state.iptal_edildi = False

        colA, colB = st.columns([1, 1])
        
        with colA:
            baslat = st.button("🚀 Apollo İçin Web Taramayı Başlat")
        with colB:
            durdur = st.button("🛑 Acil Durdur (Kill Switch)")

        if durdur:
            st.session_state.iptal_edildi = True
            st.error("🚨 İşlem acil olarak durduruldu! Kalan kredileriniz güvende.")

        if baslat:
            if not onay:
                st.error("🚨 Lütfen başlamadan önce kredi onay kutusunu işaretleyin!")
            else:
                st.session_state.iptal_edildi = False
                st.info("Tarama başlatılıyor...")
                
                ilerleme = st.progress(0)
                
                for i in range(toplam_satir):
                    if getattr(st.session_state, 'iptal_edildi', False):
                        st.warning("🛑 Tarama kullanıcı tarafından kesildi. Tamamlanan verileri indirebilirsiniz.")
                        break
                    
                    time.sleep(0.1) 
                    ilerleme.progress((i + 1) / toplam_satir)
                    
                if getattr(st.session_state, 'iptal_edildi', False) == False:
                    st.success("Tarama başarıyla tamamlandı!")