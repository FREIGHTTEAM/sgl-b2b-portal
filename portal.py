import streamlit as st
import pandas as pd
import requests
from rapidfuzz import process, fuzz
import time
import io
import json

# --- SABİT API ANAHTARI (SİSTEME GÖMÜLÜ) ---
SERPER_API_KEY = "a73b378f102b03feea358827df0eb587a7a1b7c6"

# --- SAYFA YAPILANDIRMASI ---
st.set_page_config(page_title="SGL B2B Operasyon Portalı", layout="wide")

# --- GÜVENLİK VE GİRİŞ ---
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

# --- SEKMELER ---
tab1, tab2 = st.tabs(["👥 1. Adım: Cari Ayıklama (RapidFuzz)", "🌍 2. Adım: Web Bulucu (Önbellekli)"])

# --- 1. ADIM: CARİ AYIKLAMA (RAPIDFUZZ) ---
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
            
        eslesme_esigi = st.slider("Kabul Edilebilir Minimum Benzerlik Skoru (%)", min_value=50