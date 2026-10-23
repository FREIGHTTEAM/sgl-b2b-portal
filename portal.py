import streamlit as st
import pandas as pd
import requests
import re
import time
import urllib.parse
import io
import concurrent.futures
import psycopg2 # YENİ: Bulut veritabanı kütüphanesi
import threading
import difflib

# ================= 0. GİRİŞ EKRANI (GÜVENLİK) =================
st.set_page_config(page_title="SGL B2B Portal", page_icon="🎯", layout="wide")

# Şifre kontrolü
if "logged_in" not in st.session_state:
    st.session_state.logged_in = False

if not st.session_state.logged_in:
    st.markdown("<h2 style='text-align: center;'>🎯 SGL B2B Portalına Giriş</h2>", unsafe_allow_html=True)
    st.markdown("<p style='text-align: center;'>Lütfen yetkili erişim şifresini girin.</p>", unsafe_allow_html=True)
    
    col1, col2, col3 = st.columns([1, 1, 1])
    with col2:
        # Şifreyi güvenlik için Streamlit Secrets'tan alacağız (Şimdilik test için koda yazıyoruz)
        GIZLI_SIFRE = "Sgl2026!" 
        
        girilen_sifre = st.text_input("Şifre:", type="password")
        if st.button("Giriş Yap", use_container_width=True):
            if girilen_sifre == GIZLI_SIFRE:
                st.session_state.logged_in = True
                st.rerun()
            else:
                st.error("❌ Hatalı şifre, lütfen tekrar deneyin.")
    st.stop() # Şifre girilmeden aşağıyı okumaz

# Eğer giriş yapıldıysa buraya geçer:
st.title("🎯 SGL B2B Operasyon & Veri Zenginleştirme Portalı")

try:
    from rapidfuzz import process, fuzz
except ImportError:
    st.error("Lütfen terminalden 'pip install rapidfuzz' komutunu çalıştırın.")
    st.stop()

# ================= 1. BULUT VERİTABANI BAĞLANTISI (SUPABASE) =================
# Canlıya alırken bu URL'yi Streamlit Secrets içine taşıyacağız
DB_URL = st.secrets["DB_URL"] if "DB_URL" in st.secrets else None

def get_db_connection():
    if not DB_URL:
        # DB_URL yoksa geçici olarak veritabanı kullanma (Test aşaması)
        return None
    try:
        conn = psycopg2.connect(DB_URL)
        with conn.cursor() as cur:
            cur.execute('''CREATE TABLE IF NOT EXISTS web_cache 
                         (company_name TEXT, country_code TEXT, website TEXT, score REAL, 
                         PRIMARY KEY(company_name, country_code))''')
        conn.commit()
        return conn
    except Exception as e:
        st.error(f"Veritabanı bağlantı hatası: {e}")
        return None

db_lock = threading.Lock()
conn = get_db_connection()

def clear_cache():
    if conn:
        with db_lock:
            with conn.cursor() as cur:
                cur.execute("DELETE FROM web_cache")
            conn.commit()

# ================= 2. ÜLKE LİSTESİ VE SABİTLER =================
GLOBAL_COUNTRY_DICT = {
    "Amerika Birleşik Devletleri (US)": "US", "Türkiye (TR)": "TR", "Almanya (DE)": "DE", 
    "Birleşik Krallık (GB)": "GB", "İtalya (IT)": "IT", "Fransa (FR)": "FR", "Çin (CN)": "CN", 
    "Kanada (CA)": "CA", "Avustralya (AU)": "AU", "Rusya (RU)": "RU", "Brezilya (BR)": "BR", 
    "Hindistan (IN)": "IN", "Japonya (JP)": "JP", "Güney Kore (KR)": "KR"
}

GENERIC_WORDS = {
    'TURK', 'TURKIYE', 'EGE', 'MARMARA', 'AK', 'OZ', 'DELTA', 'GLOBAL', 'STAR', 'AVRASYA', 
    'ANADOLU', 'KORFEZ', 'ASYA', 'AVRUPA', 'SAFE', 'YENI', 'ILK', 'TEK', 'BEST', 'SUPER', 
    'MEGA', 'ULTRA', 'SUN', 'LIDER', 'AY', 'GUR', 'KENT', 'DOGU', 'BATI', 'GUNEY', 'KUZEY', 'SAN', 'TIC',
    'INTERNATIONAL', 'INDUSTRIES', 'COSMETICS', 'EXPRESS', 'TRADE', 'TRADING', 'GROUP', 'LOGISTICS', 
    'SERVICES', 'FOODS', 'FOOD', 'MACHINERY', 'MACHINE', 'SYSTEMS', 'SOLUTIONS', 'PLASTICS', 'METALS',
    'CARGO', 'PACKAGING', 'PACK', 'MANUFACTURING', 'SUPPLY', 'DISTRIBUTOR', 'STONE', 'HOME',
    'MILLS', 'INNOVATION', 'CHEMSON', 'CHEMICALS', 'INGREDIENTS', 'CONSTRUCTION', 'NATURAL', 'MARBLE',
    'GLASS', 'TIRE', 'BANK', 'BANKING', 'PAPER', 'TILE', 'RUG', 'RUGS', 'CERAMIC', 'CERAMICS', 
    'PRODUCT', 'PRODUCTS', 'DISTRIBUTION', 'DESIGN', 'DESIGNS', 'LUMBER', 'GEAR'
}

BLACKLIST_DOMAINS = {
    'google.com', 'bing.com', 'yahoo.com', 'yandex.ru', 'facebook.com', 'instagram.com', 
    'twitter.com', 'x.com', 'linkedin.com', 'youtube.com', 'wikipedia.org', 'amazon.com', 
    'zoominfo.com', 'dnb.com', 'bloomberg.com', 'yelp.com', 'yellowpages.com', 'bizapedia.com', 
    'bbb.org', 'foursquare.com', 'kompass.com', 'crunchbase.com', 'bizprofile.net', 'apollo.io', 
    'trendyol.com', 'sahibinden.com', 'sikayetvar.com'
}

# ================= 3. CARİ VE YASAL TEMİZLEYİCİ =================
def normalize_turkish_lower(text):
    return str(text).replace('İ', 'i').replace('I', 'ı').replace('Ğ', 'ğ').replace('Ü', 'ü').replace('Ş', 'ş').replace('Ö', 'ö').lower()

def clean_company_universal(name):
    if not name or pd.isna(name) or str(name).strip() == "": return ""
    u = str(name).upper()
    tr_map = {'İ': 'I', 'I': 'I', 'ı': 'I', 'i': 'I', 'ş': 'S', 'Ş': 'S', 'ğ': 'G', 'Ğ': 'G', 'ü': 'U', 'Ü': 'U', 'ö': 'O', 'Ö': 'O', 'ç': 'C', 'Ç': 'C'}
    for k, v in tr_map.items(): u = u.replace(k, v)
    
    u = u.replace('&', '').replace('.', '').replace('-', '').replace("'", "")
    u = re.sub(r'\(.*?\)|\[.*?\]', ' ', u)
    
    legal_patterns = [
        r'\bANONIM\s+SIRKETI\b', r'\bLIMITED\s+SIRKETI\b', r'\bSANAYI\s+VE\s+TICARET\b',
        r'\bSANAYI\s+TICARET\b', r'\bTICARET\s+VE\s+SANAYI\b', r'\bSAN\s*VE\s*TIC\b', r'\bSAN\s*TIC\b',
        r'\bDIS\s+TICARET\b', r'\bA\s*S\b', r'\bLTD\s*STI\b', r'\bSANAYI\b', r'\bTICARETI?\b',
        r'\bCORPORATION\b', r'\bCORP\b', r'\bINCORPORATED\b', r'\bINC\b', r'\bLLC\b', 
        r'\bCOMPANY\b', r'\bCO\b', r'\bLIMITED\b', r'\bGMBH\b', r'\bUSA\b', r'\bUS\b', r'\bTR\b',
        r'\bADI\s+ORTAKLIGI\b' 
    ]
    for pat in legal_patterns:
        u = re.sub(pat, ' ', u, flags=re.IGNORECASE)
        
    u = re.sub(r'[^A-Z0-9\s]', ' ', u)
    words = [w for w in u.split() if len(w) > 1 or w.isdigit()]
    return " ".join(words)

# ================= 4. AKILLI EŞLEŞTİRME MOTORU =================
def get_best_match(th_clean, cari_dict):
    best_score = 0
    best_match = None
    
    th_words = th_clean.split()
    t_set = set(th_words)
    th_digits = set(re.findall(r'\d+', th_clean))
    
    for c_orig, c_clean in cari_dict.items():
        if not c_clean: continue
        
        base_score = fuzz.token_set_ratio(th_clean, c_clean)
        
        if base_score < 70:
            if base_score > best_score:
                best_score = base_score
                best_match = c_orig
            continue
            
        c_words = c_clean.split()
        c_set = set(c_words)
        c_digits = set(re.findall(r'\d+', c_clean))
        
        if th_digits != c_digits: base_score -= 25
            
        if len(th_words) == 1 and th_words[0] in GENERIC_WORDS: base_score -= 40
        if len(c_words) == 1 and c_words[0] in GENERIC_WORDS: base_score -= 40
        
        word_diff = abs(len(th_words) - len(c_words))
        if base_score >= 88:
            if word_diff >= 3:
                base_score -= 25 
            elif word_diff == 2 and min(len(th_words), len(c_words)) <= 2:
                base_score -= 20 
                
        t_diff = t_set - c_set
        t_diff_dist = [w for w in t_diff if w not in GENERIC_WORDS and not w.isdigit()]
        
        if t_diff_dist:
            penalty = 0
            for tw in t_diff_dist:
                max_sim = max([fuzz.ratio(tw, cw) for cw in c_set] + [0])
                if max_sim < 80: penalty += 35 
            base_score -= penalty
            
        if base_score > best_score:
            best_score = base_score
            best_match = c_orig
            if best_score >= 100: break
            
    return best_match, max(0, best_score)

# ================= 5. APOLLO KÖK DOMAIN & PUANLAMA =================
def extract_root_domain(url):
    if not url: return None
    try:
        parsed = urllib.parse.urlparse(url if "://" in url else f"http://{url}")
        netloc = parsed.netloc.lower()
        if not netloc: return None
        if netloc.endswith(('.gov', '.edu', '.mil', '.gov.tr', '.edu.tr', '.bel.tr')): return None
        
        parts = netloc.split('.')
        if len(parts) > 2:
            if parts[-2] in ['co', 'com', 'org', 'net', 'edu', 'gov'] or len(parts[-2]) <= 2:
                root = ".".join(parts[-3:])
            else:
                root = ".".join(parts[-2:])
        else:
            root = netloc
            
        root = re.sub(r'^(www\.|m\.)', '', root)
        if root in BLACKLIST_DOMAINS: return None
        return root
    except: return None

def score_and_validate_result(cleaned_company_name, result_item, target_country):
    tokens = [w for w in cleaned_company_name.split() if (len(w) > 1 or w.isdigit())]
    if not tokens: return 0, None
        
    link = result_item.get("link", "")
    title_clean = clean_company_universal(result_item.get("title", "")).lower()
    snippet_clean = clean_company_universal(result_item.get("snippet", "")).lower()
    
    root_domain = extract_root_domain(link)
    if not root_domain: return 0, None
        
    domain_body = root_domain.split('.')[0].replace('-', '').replace('_', '')
    score = 0
    concat_tokens = "".join(tokens).lower()
    digit_tokens = [t for t in tokens if any(c.isdigit() for c in t)]
    
    if domain_body == concat_tokens: score += 70
    elif concat_tokens in domain_body: score += 50
    elif domain_body in concat_tokens:
        if not digit_tokens: score += 25
        else: score -= 35 
            
    tokens_in_domain = [t for t in tokens if t.lower() in domain_body]
    score += len(tokens_in_domain) * 20
    
    for dt in digit_tokens:
        if dt in domain_body: score += 30
        elif dt in title_clean: score += 15
        else: score -= 40
    
    full_name_clean = " ".join(tokens).lower()
    if full_name_clean in title_clean: score += 45
    elif all(t.lower() in title_clean for t in tokens): score += 35
    if full_name_clean in snippet_clean: score += 25
        
    netloc_parts = root_domain.split('.')
    if target_country == "TR" and ('tr' in netloc_parts): score += 30
    elif target_country == "GB" and ('uk' in netloc_parts): score += 30
    elif target_country == "DE" and ('de' in netloc_parts): score += 30
    elif target_country != "US" and target_country.lower() in netloc_parts: score += 20
        
    return min(score, 100), root_domain

def serper_google_search(company_name, api_key, country_suffix="US"):
    cleaned_name = clean_company_universal(company_name)
    if not cleaned_name: return None, 0

    words_upper = cleaned_name.split()
    query = f"{cleaned_name} {country_suffix}" if country_suffix not in words_upper else cleaned_name
    lang = "tr" if country_suffix == "TR" else "en"
    
    url = "https://google.serper.dev/search"
    payload = {"q": query, "gl": "us" if country_suffix == "US" else country_suffix.lower(), "hl": lang, "num": 8}
    headers = {'X-API-KEY': api_key.strip(), 'Content-Type': 'application/json'}
    
    for attempt in range(3):
        try:
            response = requests.post(url, headers=headers, json=payload, timeout=10)
            if response.status_code == 429:
                time.sleep(2.0 * (attempt + 1))
                continue
            if response.status_code in [401, 403, 400]:
                return "API_ERROR", 0
                
            if response.status_code == 200:
                data = response.json()
                best_score = 0
                best_url = None
                
                kg = data.get("knowledgeGraph", {})
                if kg and "website" in kg:
                    kg_score, kg_url = score_and_validate_result(cleaned_name, {"link": kg["website"], "title": kg.get("title", ""), "snippet": ""}, country_suffix)
                    if kg_score >= 35: return kg_url, kg_score

                for item in data.get("organic", []):
                    score, clean_url = score_and_validate_result(cleaned_name, item, country_suffix)
                    if score > best_score:
                        best_score = score
                        best_url = clean_url
                        
                if best_score >= 35: return best_url, best_score
                return None, 0
        except Exception:
            time.sleep(1.0)
            
    return "NETWORK_ERROR", 0

# ================= 6. ARAYÜZ YÖNETİMİ =================
if "df_kesin" not in st.session_state: st.session_state.df_kesin = None
if "df_supheli" not in st.session_state: st.session_state.df_supheli = None
if "df_yeni" not in st.session_state: st.session_state.df_yeni = None
if "df_web_sonuc" not in st.session_state: st.session_state.df_web_sonuc = None

sekme1, sekme2 = st.tabs(["👥 1. Adım: Cari Ayıklama (RapidFuzz)", "🌍 2. Adım: Web Bulucu (Önbellekli)"])

with sekme1:
    st.markdown("Hedef listenizi **Ağırlaştırılmış Boyut Cezası** ile hatasız ayıklayın.")
    col1, col2 = st.columns(2)
    with col1: dosya_hedef = st.file_uploader("1️⃣ Hedef Liste (Excel/CSV)", key="hedef")
    with col2: dosya_cari = st.file_uploader("2️⃣ SGL CARİLER (Excel/CSV)", key="cari")

    if dosya_hedef and dosya_cari:
        df_hedef = pd.read_excel(dosya_hedef) if dosya_hedef.name.endswith(('xlsx','xls')) else pd.read_csv(dosya_hedef)
        df_cari = pd.read_excel(dosya_cari) if dosya_cari.name.endswith(('xlsx','xls')) else pd.read_csv(dosya_cari)
        
        c_hedef = st.selectbox("Hedef Listede Firma Adı Sütunu:", df_hedef.columns, index=0)
        c_cari = st.selectbox("SGL CARİLER'de Firma Adı Sütunu:", df_cari.columns, index=list(df_cari.columns).index("Firma Adı") if "Firma Adı" in df_cari.columns else 0)

        if st.button("Sıfır Adayları Ayıkla ⚙️"):
            status = st.empty()
            progress = st.progress(0)
            
            cari_dict = {str(orig): clean_company_universal(orig) for orig in df_cari[c_cari].dropna()}
            kat_kesin, kat_supheli, kat_yeni = [], [], []
            toplam = len(df_hedef)

            for index, row in df_hedef.iterrows():
                if index % 50 == 0: progress.progress((index + 1) / toplam)
                
                orijinal_hedef = str(row[c_hedef])
                th_clean = clean_company_universal(orijinal_hedef)
                satir_dict = row.to_dict()
                
                if not th_clean or th_clean in GENERIC_WORDS:
                    satir_dict['Durum'] = "🟢 Yeni Aday"
                    kat_yeni.append(satir_dict)
                    continue
                
                eslesen_orijinal, final_score = get_best_match(th_clean, cari_dict)
                
                if eslesen_orijinal and final_score >= 75:
                    satir_dict['Eşleşen Cari'] = eslesen_orijinal
                    satir_dict['Benzerlik Skoru'] = f"%{int(final_score)}"
                    
                    if final_score >= 88:
                        satir_dict['Durum'] = "🔴 Kesin Müşteri"
                        kat_kesin.append(satir_dict)
                    else:
                        satir_dict['Durum'] = "🟡 Şüpheli (İncele)"
                        kat_supheli.append(satir_dict)
                else:
                    satir_dict['Durum'] = "🟢 Sıfır Aday"
                    satir_dict['Eşleşen Cari'] = "-"
                    satir_dict['Benzerlik Skoru'] = "-"
                    kat_yeni.append(satir_dict)

            progress.progress(1.0)
            status.success("✅ Ayıklama Tamamlandı!")
            
            st.session_state.df_kesin = pd.DataFrame(kat_kesin)
            st.session_state.df_supheli = pd.DataFrame(kat_supheli)
            st.session_state.df_yeni = pd.DataFrame(kat_yeni)

    if st.session_state.df_kesin is not None:
        c1, c2, c3 = st.columns(3)
        with c1:
            st.error(f"🔴 Kesin Müşteriler: {len(st.session_state.df_kesin)}")
            if not st.session_state.df_kesin.empty:
                out = io.BytesIO(); st.session_state.df_kesin.to_excel(out, index=False); out.seek(0)
                st.download_button("İndir", out, "3_Kesin_Musteriler.xlsx", key="dl_kesin")
        with c2:
            st.warning(f"🟡 Şüpheliler (İncele): {len(st.session_state.df_supheli)}")
            if not st.session_state.df_supheli.empty:
                out = io.BytesIO(); st.session_state.df_supheli.to_excel(out, index=False); out.seek(0)
                st.download_button("İndir", out, "2_Supheli_Inceleme.xlsx", key="dl_suphe")
        with c3:
            st.success(f"🟢 SIFIR YENİ ADAYLAR: {len(st.session_state.df_yeni)}")
            if not st.session_state.df_yeni.empty:
                out = io.BytesIO(); st.session_state.df_yeni.to_excel(out, index=False); out.seek(0)
                st.download_button("İndir", out, "1_Sifir_Yeni_Adaylar.xlsx", key="dl_yeni")

with sekme2:
    st.markdown("Global ve Yerel alıcıların web sitelerini **Apollo Formatında (Domain)** bulun.")
    
    col_k1, col_k2, col_k3 = st.columns([2, 1, 1])
    with col_k1: api_key_gb = st.text_input("🔑 Serper API Anahtarı", type="password")
    with col_k2:
        secilen_ulke_label = st.selectbox("🌍 Hedef Ülke", options=list(GLOBAL_COUNTRY_DICT.keys()))
        secilen_kod = GLOBAL_COUNTRY_DICT[secilen_ulke_label]
    with col_k3:
        st.write(""); st.write("")
        if st.button("🗑️ Önbelleği Temizle"):
            clear_cache()
            st.success("Önbellek temizlendi!")

    file_global = st.file_uploader("Sıfır Aday Listesi (Excel/CSV) Yükleyin", type=["xlsx", "xls", "csv"])

    if file_global is not None:
        df_gb = pd.read_excel(file_global) if file_global.name.endswith(('xlsx', 'xls')) else pd.read_csv(file_global)
        sutun_gb = st.selectbox("Web Taraması İçin Firma Adı Sütunu:", df_gb.columns, index=0)
        
        if 'Company Name' not in df_gb.columns: df_gb['Company Name'] = df_gb[sutun_gb]
        if 'Company Website' not in df_gb.columns: df_gb['Company Website'] = ''
        if 'Güven Skoru' not in df_gb.columns: df_gb['Güven Skoru'] = ''
        if 'Kategori' not in df_gb.columns: df_gb['Kategori'] = ''
            
        if st.button(f"🚀 Apollo İçin Web Taramayı Başlat ({secilen_kod})"):
            if not api_key_gb.strip():
                st.error("❌ Tarama yapılamadı: API Anahtarı eksik.")
                st.stop()

            if not conn:
                st.warning("⚠️ Bulut Veritabanı bağlı değil! Önbellek kullanılamıyor, her arama kredinizden düşecek.")

            abort_event = threading.Event()
            prog_gb = st.progress(0)
            col_m1, col_m2, col_m3, col_m4 = st.columns(4)
            with col_m1: m1_gb = st.empty()
            with col_m2: m2_gb = st.empty()
            with col_m3: m3_tr = st.empty()
            with col_m4: m4_gb = st.empty()
            
            toplam_gb = len(df_gb)
            tamamlanan_gb, bulunan_gb, cache_gb = 0, 0, 0
            
            def worker_gb(idx, isim):
                if abort_event.is_set() or pd.isna(isim): return idx, None, 0, False
                
                # 1. Cache kontrol (DB bağlıysa)
                if conn:
                    with db_lock:
                        with conn.cursor() as cur:
                            cur.execute("SELECT website, score FROM web_cache WHERE company_name=%s AND country_code=%s", (isim, secilen_kod))
                            row = cur.fetchone()
                        if row: return idx, row[0], row[1], True 
                
                time.sleep(0.12)
                url, score = serper_google_search(isim, api_key_gb, secilen_kod)
                
                if url in ["API_ERROR", "NETWORK_ERROR"]: 
                    if url == "API_ERROR": abort_event.set()
                    return idx, url, 0, False 
                
                # 2. Yeni sonucu kaydet (DB bağlıysa)
                if conn and url:
                    with db_lock:
                        with conn.cursor() as cur:
                            cur.execute("""
                                INSERT INTO web_cache (company_name, country_code, website, score) 
                                VALUES (%s, %s, %s, %s) 
                                ON CONFLICT (company_name, country_code) 
                                DO UPDATE SET website=EXCLUDED.website, score=EXCLUDED.score
                            """, (isim, secilen_kod, url, score))
                        conn.commit()
                return idx, url, score, False

            with concurrent.futures.ThreadPoolExecutor(max_workers=4) as executor:
                gelecekler = {executor.submit(worker_gb, idx, row[sutun_gb]): idx for idx, row in df_gb.iterrows()}
                
                for f in concurrent.futures.as_completed(gelecekler):
                    if abort_event.is_set(): continue
                    i, site, score, from_cache = f.result()
                    
                    if site == "API_ERROR": continue
                    if from_cache: cache_gb += 1
                    
                    if site == "NETWORK_ERROR":
                        df_gb.at[i, 'Company Website'] = ""
                        df_gb.at[i, 'Kategori'] = "⚠️ Hata (Tekrar Dene)"
                        df_gb.at[i, 'Güven Skoru'] = "-"
                    elif site and score >= 35:
                        df_gb.at[i, 'Company Website'] = site
                        df_gb.at[i, 'Güven Skoru'] = f"%{int(score)}"
                        df_gb.at[i, 'Kategori'] = "✅ Güvenilir" if score >= 65 else "🟡 Şüpheli"
                        bulunan_gb += 1
                    else:
                        df_gb.at[i, 'Company Website'] = ""
                        df_gb.at[i, 'Kategori'] = "❌ Bulunamadı"
                        df_gb.at[i, 'Güven Skoru'] = "-"
                        
                    tamamlanan_gb += 1
                    prog_gb.progress(tamamlanan_gb / toplam_gb)
                    
                    m1_gb.metric("İşlenen", f"{tamamlanan_gb} / {toplam_gb}")
                    m2_gb.metric("Bulunan (Kök Domain)", f"✅ {bulunan_gb}")
                    m3_tr.metric("Önbellekten", f"⚡ {cache_gb}")
                    m4_gb.metric("Başarı Oranı", f"%{(bulunan_gb / tamamlanan_gb * 100):.1f}" if tamamlanan_gb > 0 else "%0")

            if abort_event.is_set():
                st.error("🚨 API Hatası: Anahtar geçersiz veya kotanız doldu. Tarama durduruldu.")
            else:
                st.success("🎉 Tarama Tamamlandı!")
            st.session_state.df_web_sonuc = df_gb

    if st.session_state.df_web_sonuc is not None:
        df_apollo = st.session_state.df_web_sonuc.copy()
        df_apollo = df_apollo[df_apollo['Kategori'] == "✅ Güvenilir"]
        
        c_down1, c_down2 = st.columns(2)
        with c_down1:
            out_gb = io.BytesIO()
            df_apollo.to_csv(out_gb, index=False, encoding='utf-8-sig')
            out_gb.seek(0)
            st.download_button(f"📥 Apollo'ya Hazır CSV İndir ({len(df_apollo)} Firma)", out_gb, "Apollo_Aktarim_Listesi.csv", "text/csv")
        with c_down2:
            out_full = io.BytesIO()
            st.session_state.df_web_sonuc.to_excel(out_full, index=False)
            out_full.seek(0)
            st.download_button("Tüm Sonuçları İndir (Bulunamayanlar ve Hatalar Dahil)", out_full, "Tum_Web_Taramasi.xlsx")