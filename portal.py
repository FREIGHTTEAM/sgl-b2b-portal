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
            
            df_eslesen = df_sonuc[df_sonuc["Durum"] == "✅ Eşleşti"]
            df_eslesmeyen = df_sonuc[df_sonuc["Durum"] == "❌ Eşleşmedi"]
            df_eslesmeyen_sade = df_eslesmeyen[["Firma Adı"]]
            
            tab_e, tab_y = st.tabs([f"✅ Eşleşenler ({len(df_eslesen)})", f"❌ Yeni Potansiyel ({len(df_eslesmeyen_sade)})"])
            with tab_e:
                st.dataframe(df_eslesen)
            with tab_y:
                st.dataframe(df_eslesmeyen_sade)
            
            st.markdown("### 📥 Sonuçları İndir (Excel Formatında)")
            dl_col1, dl_col2 = st.columns(2)
            
            with dl_col1:
                buffer_eslesen = io.BytesIO()
                df_eslesen.to_excel(buffer_eslesen, index=False, engine='openpyxl')
                st.download_button(
                    label="📥 Eşleşen Carileri İndir (Detaylı Excel)",
                    data=buffer_eslesen.getvalue(),
                    file_name="Cari_Eslesenler.xlsx",
                    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                )
                
            with dl_col2:
                buffer_eslesmeyen = io.BytesIO()
                df_eslesmeyen_sade.to_excel(buffer_eslesmeyen, index=False, engine='openpyxl')
                st.download_button(
                    label="📥 Eşleşmeyenleri İndir (Sadece Firma Adı - Excel)",
                    data=buffer_eslesmeyen.getvalue(),
                    file_name="Sifir_Aday_Listesi.xlsx",
                    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                )

# --- 2. ADIM: WEB BULUCU VE KILL SWITCH ---
with tab2:
    st.markdown("Global ve Yerel alıcıların web sitelerini **Apollo Formatında (Domain)** bulun.")
    
    hedef_ulke = st.selectbox("🌍 Hedef Ülke", [
        "Amerika Birleşik Devletleri (US)", 
        "Birleşik Krallık (UK)", 
        "Almanya (DE)", 
        "Türkiye (TR)", 
        "Global (Ülke Belirtme)"
    ])
    
    web_file = st.file_uploader("Sıfır Aday Listesi (Excel/CSV) Yükleyin", key="web")
    
    if web_file:
        df_web = pd.read_excel(web_file) if web_file.name.endswith('.xlsx') else pd.read_csv(web_file)
        sutun = st.selectbox("Web Taraması İçin Firma Adı Sütunu:", df_web.columns)
        
        toplam_satir = len(df_web)
        st.warning(f"⚠️ DİKKAT: Yüklediğiniz dosyada **{toplam_satir}** firma bulunuyor. Bu işlem Serper'den yaklaşık **{toplam_satir}** kredi harcayacaktır.")
        
        onay = st.checkbox("Kredi maliyetini gördüm, taramayı başlatmayı onaylıyorum.")
        
        if 'iptal_edildi' not in st.session_state:
            st.session_state.iptal_edildi = False

        colA, colB = st.columns([1, 1])
        
        ulke_kodu = hedef_ulke.split("(")[-1].replace(")", "")
        buton_metni = f"🚀 Apollo İçin Web Taramayı Başlat" if ulke_kodu == "Ülke Belirtme" else f"🚀 Apollo İçin Web Taramayı Başlat ({ulke_kodu})"
        
        with colA:
            baslat = st.button(buton_metni)
        with colB:
            durdur = st.button("🛑 Acil Durdur (Kill Switch)")

        if durdur:
            st.session_state.iptal_edildi = True
            st.error("🚨 İşlem acil olarak durduruldu! Kalan kredileriniz güvende.")

        if baslat:
            if not onay:
                st.error("🚨 Lütfen başlamadan önce kredi onay kutusunu işaretleyin!")
            elif SERPER_API_KEY == "BURAYA_YAPIŞTIRIN":
                st.error("🚨 Lütfen portal.py dosyasının en üstündeki SERPER_API_KEY değişkenine kendi API anahtarınızı ekleyin!")
            else:
                st.session_state.iptal_edildi = False
                st.info("Tarama başlatılıyor...")
                
                ilerleme = st.progress(0)
                tarama_sonuclari = []
                
                for i in range(toplam_satir):
                    if getattr(st.session_state, 'iptal_edildi', False):
                        st.warning("🛑 Tarama kullanıcı tarafından kesildi. Şu ana kadar bulunan verileri aşağıdan indirebilirsiniz.")
                        break
                    
                    firma_adi = str(df_web.iloc[i][sutun])
                    arama_terimi = f"{firma_adi} company website"
                    if ulke_kodu != "Ülke Belirtme":
                        arama_terimi += f" {ulke_kodu}"
                    
                    # GERÇEK SERPER API BAĞLANTISI
                    url = "https://google.serper.dev/search"
                    payload = json.dumps({"q": arama_terimi, "num": 1})
                    headers = {
                        'X-API-KEY': SERPER_API_KEY,
                        'Content-Type': 'application/json'
                    }
                    
                    try:
                        response = requests.post(url, headers=headers, data=payload)
                        data = response.json()
                        domain = data.get("organic", [])[0].get("link", "Bulunamadı")
                    except:
                        domain = "Bağlantı Hatası"
                    
                    tarama_sonuclari.append({
                        "Firma Adı": firma_adi,
                        "Bulunan Web Sitesi": domain
                    })
                    
                    ilerleme.progress((i + 1) / toplam_satir)
                    
                if getattr(st.session_state, 'iptal_edildi', False) == False:
                    st.success("Tarama başarıyla tamamlandı!")
                
                # SONUÇLARI GÖSTER VE İNDİR
                if tarama_sonuclari:
                    df_sonuc_web = pd.DataFrame(tarama_sonuclari)
                    st.dataframe(df_sonuc_web)
                    
                    buffer_web = io.BytesIO()
                    df_sonuc_web.to_excel(buffer_web, index=False, engine='openpyxl')
                    st.download_button(
                        label="📥 Bulunan Web Sitelerini İndir (Excel)",
                        data=buffer_web.getvalue(),
                        file_name="Firma_Web_Siteleri.xlsx",
                        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                    )