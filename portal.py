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
        st.success("Dosyalar yüklendi. Eşleştirme algoritması burada çalışacak.")

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
                    
                    # API ÇAĞRISI BURADA YAPILACAK (Simülasyon için sleep eklendi)
                    time.sleep(0.1) 
                    ilerleme.progress((i + 1) / toplam_satir)
                    
                if getattr(st.session_state, 'iptal_edildi', False) == False:
                    st.success("Tarama başarıyla tamamlandı!")