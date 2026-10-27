import streamlit as st
import pandas as pd
import requests
from rapidfuzz import process, fuzz
import time
import io
import json
import os
import urllib.parse
from sqlalchemy import create_engine

# --- SABİT API ANAHTARI VE AYARLAR ---
SERPER_API_KEY = "a73b378f102b03feea358827df0eb587a7a1b7c6"
CACHE_DOSYASI = "domain_cache.json"
SUPABASE_URL = "postgresql://postgres.sfuauyfobwzhtydyfdnh:SglPortal2026!@aws-0-eu-west-1.pooler.supabase.com:6543/postgres"

YASAKLI_SITELER = [
    "linkedin.com", "facebook.com", "instagram.com", "twitter.com", "x.com", "youtube.com", 
    "zoominfo.com", "dnb.com", "bloomberg.com", "crunchbase.com", "apollo.io", 
    "glassdoor.com", "yellowpages.com", "yelp.com", "kompass.com", "tr.foursquare.com", 
    "google.com", "mapquest.com", "bbb.org", "chamberofcommerce.com", "yahoo.com"
]

st.set_page_config(page_title="SGL B2B Operasyon Portalı", layout="wide")

def bellek_yukle():
    if os.path.exists(CACHE_DOSYASI):
        with open(CACHE_DOSYASI, "r", encoding="utf-8") as f:
            return json.load(f)
    return {}

def bellek_kaydet(veri):
    with open(CACHE_DOSYASI, "w", encoding="utf-8") as f:
        json.dump(veri, f, ensure_ascii=False, indent=4)

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
        
        s_col1, s_col2 = st.columns(2)
        with s_col1:
            hedef_sutun = st.selectbox("Hedef Listedeki Firma Adı Sütunu:", df_hedef.columns)
        with s_col2:
            cari_sutun = st.selectbox("SGL Cari Listesindeki Firma Adı Sütunu:", df_cari.columns)
            
        eslesme_esigi = st.slider("Cari Benzerlik Skoru (%)", min_value=50, max_value=100, value=85)
        
        if st.button("🔍 Eşleştirmeyi Başlat"):
            ilerleme = st.progress(0)
            hedef_firmalar = df_hedef[hedef_sutun].dropna().astype(str).tolist()
            cari_firmalar = df_cari[cari_sutun].dropna().astype(str).tolist()
            sonuclar = []
            toplam = len(hedef_firmalar)
            
            for i, firma in enumerate(hedef_firmalar):
                eslesme = process.extractOne(firma, cari_firmalar, scorer=fuzz.token_sort_ratio)
                if eslesme and eslesme[1] >= eslesme_esigi:
                    sonuclar.append({"Firma Adı": firma, "SGL Cari": eslesme[0], "Skor": round(eslesme[1], 2), "Durum": "✅"})
                else:
                    sonuclar.append({"Firma Adı": firma, "SGL Cari": "-", "Skor": round(eslesme[1], 2) if eslesme else 0, "Durum": "❌"})
                if i % 20 == 0 or i == toplam - 1:
                    ilerleme.progress((i + 1) / toplam)
                    
            df_sonuc = pd.DataFrame(sonuclar)
            df_eslesen = df_sonuc[df_sonuc["Durum"] == "✅"]
            df_eslesmeyen_sade = df_sonuc[df_sonuc["Durum"] == "❌"][["Firma Adı"]]
            
            st.success("Eşleştirme Tamamlandı!")
            dl_col1, dl_col2, db_col = st.columns(3)
            
            with dl_col1:
                buf_e = io.BytesIO()
                df_eslesen.to_excel(buf_e, index=False, engine='openpyxl')
                st.download_button("📥 Eşleşenleri İndir", data=buf_e.getvalue(), file_name="Cari_Eslesenler.xlsx")
            with dl_col2:
                buf_y = io.BytesIO()
                df_eslesmeyen_sade.to_excel(buf_y, index=False, engine='openpyxl')
                st.download_button("📥 Sıfır Aday Listesi İndir", data=buf_y.getvalue(), file_name="Sifir_Aday_Listesi.xlsx")
            with db_col:
                if st.button("💾 Supabase'e Yaz (1)"):
                    try:
                        create_engine(SUPABASE_URL).execute("SELECT 1")
                        st.success("Aktif (Geliştirme Aşamasında)")
                    except Exception as e:
                        st.error(f"Hata: {e}")

# --- 2. ADIM: WEB BULUCU VE KILL SWITCH ---
with tab2:
    st.markdown("Global alıcıların sitelerini Apollo formatında bulur ve Domain-Firma benzerliğini puanlar.")
    
    if 'kurtarilan_veriler' not in st.session_state:
        st.session_state.kurtarilan_veriler = []
        
    hedef_ulke = st.selectbox("🌍 Hedef Ülke", ["Amerika Birleşik Devletleri (US)", "Birleşik Krallık (UK)", "Almanya (DE)", "Türkiye (TR)", "Global (Ülke Belirtme)"])
    web_file = st.file_uploader("Sıfır Aday Listesi Yükleyin", key="web")
    
    if web_file:
        df_web = pd.read_excel(web_file) if web_file.name.endswith('.xlsx') else pd.read_csv(web_file)
        sutun = st.selectbox("Firma Adı Sütunu:", df_web.columns)
        
        toplam_satir = len(df_web)
        domain_guvenlik_esigi = st.slider("Domain - Firma Adı Benzerlik Sınırı (%) (Bunun altındakiler 'Şüpheli' klasörüne ayrılır)", min_value=10, max_value=90, value=40)
        
        col_bas, col_bit = st.columns(2)
        with col_bas:
            baslangic = st.number_input("Başlangıç Satırı:", min_value=0, max_value=toplam_satir-1, value=0, step=1000)
        with col_bit:
            bitis = st.number_input("Bitiş Satırı:", min_value=1, max_value=toplam_satir, value=min(1000, toplam_satir), step=1000)
            
        islem_miktari = bitis - baslangic
        onay = st.checkbox(f"Seçili aralığı onaylıyorum (Maksimum {islem_miktari} kredi harcanabilir).")
        
        colA, colB = st.columns([1, 1])
        ulke_kodu = hedef_ulke.split("(")[-1].replace(")", "")
        buton_metni = "🚀 Apollo İçin Web Taramayı Başlat" if ulke_kodu == "Ülke Belirtme" else f"🚀 Taramayı Başlat ({ulke_kodu})"
        
        with colA:
            baslat = st.button(buton_metni)
        with colB:
            durdur = st.button("🛑 Acil Durdur")

        if durdur:
            st.session_state.iptal_edildi = True
            st.error("🚨 İşlem durduruldu!")

        if baslat and onay and islem_miktari > 0:
            st.session_state.iptal_edildi = False
            st.session_state.kurtarilan_veriler = []
            
            durum_metni = st.empty()
            ilerleme = st.progress(0)
            
            df_islem = df_web.iloc[baslangic:bitis]
            bellek_verisi = bellek_yukle()
            
            for index, (orijinal_index, row) in enumerate(df_islem.iterrows()):
                if getattr(st.session_state, 'iptal_edildi', False):
                    break
                
                firma_adi = str(row[sutun])
                arama_terimi = f"{firma_adi} company website"
                if ulke_kodu != "Ülke Belirtme":
                    arama_terimi += f" {ulke_kodu}"
                
                if arama_terimi in bellek_verisi:
                    domain = bellek_verisi[arama_terimi]
                else:
                    url = "https://google.serper.dev/search"
                    payload = json.dumps({"q": arama_terimi, "num": 5})
                    headers = {'X-API-KEY': SERPER_API_KEY, 'Content-Type': 'application/json'}
                    domain = "Bulunamadı"
                    try:
                        response = requests.post(url, headers=headers, data=payload, timeout=5)
                        organic_results = response.json().get("organic", [])
                        for sonuc in organic_results:
                            tam_url = sonuc.get("link", "")
                            if tam_url:
                                parsed_url = urllib.parse.urlparse(tam_url)
                                net_domain = parsed_url.netloc.lower()
                                if net_domain.startswith("www."): net_domain = net_domain[4:]
                                if not any(y in net_domain for y in YASAKLI_SITELER):
                                    domain = net_domain
                                    break
                    except:
                        domain = "Hata"
                    bellek_verisi[arama_terimi] = domain
                    bellek_kaydet(bellek_verisi)
                
                # FİRMA VE DOMAİN BENZERLİĞİNİ ÖLÇME
                firma_temiz = firma_adi.lower().replace("inc", "").replace("llc", "").replace("ltd", "").replace(".", "").strip()
                domain_temiz = domain.split(".")[0].lower() if domain not in ["Bulunamadı", "Hata"] else ""
                benzerlik_skoru = fuzz.token_set_ratio(firma_temiz, domain_temiz)
                guven_durumu = "Güvenilir" if benzerlik_skoru >= domain_guvenlik_esigi else "Şüpheli"
                
                st.session_state.kurtarilan_veriler.append({
                    "Firma Adı": firma_adi, 
                    "Bulunan Web Sitesi": domain,
                    "Domain Skoru": benzerlik_skoru,
                    "Kategori": guven_durumu
                })
                
                ilerleme.progress((index + 1) / islem_miktari)
                durum_metni.info(f"⏳ {index + 1}/{islem_miktari} | {firma_adi} -> {domain} (Skor: {benzerlik_skoru})")
                
            durum_metni.success("✅ Tarama ve ayıklama tamamlandı!")

        if len(st.session_state.kurtarilan_veriler) > 0:
            df_sonuc_web = pd.DataFrame(st.session_state.kurtarilan_veriler)
            
            df_guvenilir = df_sonuc_web[df_sonuc_web["Kategori"] == "Güvenilir"].drop(columns=["Kategori"])
            df_supheli = df_sonuc_web[df_sonuc_web["Kategori"] == "Şüpheli"].drop(columns=["Kategori"])
            
            tab_g, tab_s = st.tabs([f"✅ Güvenilir Siteler ({len(df_guvenilir)})", f"⚠️ Şüpheli / Manuel Kontrol ({len(df_supheli)})"])
            with tab_g: st.dataframe(df_guvenilir)
            with tab_s: st.dataframe(df_supheli)
            
            dl_col1, dl_col2 = st.columns(2)
            with dl_col1:
                buf_g = io.BytesIO()
                df_guvenilir.to_excel(buf_g, index=False, engine='openpyxl')
                st.download_button("📥 Apollo'ya Hazır (Güvenilir) İndir", data=buf_g.getvalue(), file_name="Apollo_Hazir_Siteler.xlsx")
            with dl_col2:
                buf_s = io.BytesIO()
                df_supheli.to_excel(buf_s, index=False, engine='openpyxl')
                st.download_button("📥 Şüpheli Siteleri (Manuel) İndir", data=buf_s.getvalue(), file_name="Supheli_Siteler.xlsx")