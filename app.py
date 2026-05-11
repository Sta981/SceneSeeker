import streamlit as st
import pickle
import requests
import pandas as pd
import sqlite3
import os
import re
from datetime import datetime
import streamlit.components.v1 as components

try:
    from groq import Groq as _Groq
except ImportError:
    _Groq = None

GROQ_API_KEY = st.secrets.get("GROQ_API_KEY", "")
TMDB_API_KEY = st.secrets.get("TMDB_API_KEY", "")
APP_NAME = "SceneSeeker"

LOGO_SVG = """<svg width="{size}" height="{size}" viewBox="0 0 64 64" xmlns="http://www.w3.org/2000/svg">
  <rect x="6" y="20" width="52" height="36" rx="5" fill="#1a1a1a" stroke="#e63946" stroke-width="1.5"/>
  <rect x="6" y="10" width="52" height="14" rx="5" fill="#e63946"/>
  <line x1="6" y1="17" x2="58" y2="17" stroke="#1a1a1a" stroke-width="1"/>
  <rect x="14" y="10" width="7" height="14" fill="#1a1a1a" transform="skewX(-15)"/>
  <rect x="28" y="10" width="7" height="14" fill="#1a1a1a" transform="skewX(-15)"/>
  <rect x="42" y="10" width="7" height="14" fill="#1a1a1a" transform="skewX(-15)"/>
  <circle cx="32" cy="38" r="8" fill="none" stroke="#e63946" stroke-width="2"/>
  <polygon points="29,34 29,42 38,38" fill="#e63946"/>
</svg>"""

def logo(size=40): return LOGO_SVG.format(size=size)

def _make_favicon():
    try:
        from PIL import Image, ImageDraw
        img = Image.new("RGBA", (64, 64), (0, 0, 0, 0))
        d = ImageDraw.Draw(img)
        d.rounded_rectangle([6,20,58,56], radius=5, fill="#1a1a1a", outline="#e63946", width=2)
        d.rounded_rectangle([6,10,58,24], radius=5, fill="#e63946")
        d.ellipse([24,30,40,46], outline="#e63946", width=2)
        d.polygon([(29,34),(29,42),(38,38)], fill="#e63946")
        img.save("favicon.png")
        return "favicon.png"
    except: return "🎬"

_favicon = _make_favicon()
st.set_page_config(page_title=APP_NAME, page_icon=_favicon, layout="wide", initial_sidebar_state="expanded")

st.markdown("""
<style>
    @import url('https://fonts.googleapis.com/css2?family=Playfair+Display:wght@600&display=swap');
    #MainMenu, footer, header {visibility: hidden;}
    section.main > div { padding-top: 1rem; }
    div[data-testid="column"] img { border-radius: 10px; }
    div[data-testid="metric-container"] {
        background: rgba(128,128,128,0.06); border-radius: 10px;
        padding: 0.8rem 1rem; border: 0.5px solid rgba(128,128,128,0.12);
    }
    .activity-feed { max-height: 340px; overflow-y: auto; }
    .activity-item {
        display: flex; align-items: center; gap: 10px;
        padding: 8px 0; border-bottom: 0.5px solid rgba(128,128,128,0.12);
        font-size: 13px;
    }
    .activity-avatar {
        width: 32px; height: 32px; border-radius: 50%;
        background: #e63946; color: #fff; display: flex;
        align-items: center; justify-content: center;
        font-weight: 700; font-size: 13px; flex-shrink: 0;
    }
    .activity-text { color: inherit; line-height: 1.4; }
    .activity-time { font-size: 11px; opacity: 0.45; }
    .progress-bar-outer {
        background: rgba(128,128,128,0.2); border-radius: 4px;
        height: 4px; margin-top: 4px; width: 100%;
    }
    .progress-bar-inner { background: #e63946; border-radius: 4px; height: 4px; }
    .cw-card {
        background: rgba(128,128,128,0.07); border-radius: 10px;
        padding: 10px; display: flex; gap: 12px; align-items: center;
        border: 0.5px solid rgba(128,128,128,0.12); margin-bottom: 8px;
    }
    .cw-info { flex: 1; }
    .cw-title { font-weight: 600; font-size: 14px; }
    .cw-meta { font-size: 12px; opacity: 0.5; }
</style>
""", unsafe_allow_html=True)

def get_db():
    conn = sqlite3.connect("sceneseeker.db", check_same_thread=False)
    conn.execute("CREATE TABLE IF NOT EXISTS users (id INTEGER PRIMARY KEY AUTOINCREMENT, username TEXT UNIQUE, created_at TEXT)")
    conn.execute("""CREATE TABLE IF NOT EXISTS watch_history (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER, movie_id TEXT, movie_title TEXT,
        rating REAL, watched_at TEXT, progress_seconds INTEGER DEFAULT 0,
        duration_seconds INTEGER DEFAULT 0
    )""")
    conn.execute("CREATE TABLE IF NOT EXISTS chat_history (id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER, role TEXT, message TEXT, timestamp TEXT)")
    # migration: add columns if old DB
    try: conn.execute("ALTER TABLE watch_history ADD COLUMN progress_seconds INTEGER DEFAULT 0")
    except: pass
    try: conn.execute("ALTER TABLE watch_history ADD COLUMN duration_seconds INTEGER DEFAULT 0")
    except: pass
    conn.commit()
    return conn

def get_or_create_user(username):
    conn = get_db()
    row = conn.execute("SELECT id FROM users WHERE username=?", (username,)).fetchone()
    if row: return row[0]
    conn.execute("INSERT INTO users(username,created_at) VALUES(?,?)", (username, datetime.now().isoformat()))
    conn.commit()
    return conn.execute("SELECT id FROM users WHERE username=?", (username,)).fetchone()[0]

def save_watch(user_id, movie_id, movie_title, rating=None, progress_seconds=0, duration_seconds=0):
    conn = get_db()
    existing = conn.execute("SELECT id FROM watch_history WHERE user_id=? AND movie_id=?", (user_id, str(movie_id))).fetchone()
    if existing:
        updates = []
        params  = []
        if rating:           updates.append("rating=?");           params.append(rating)
        if progress_seconds: updates.append("progress_seconds=?"); params.append(progress_seconds)
        if duration_seconds: updates.append("duration_seconds=?"); params.append(duration_seconds)
        if updates:
            params.append(existing[0])
            conn.execute(f"UPDATE watch_history SET {', '.join(updates)} WHERE id=?", params)
    else:
        conn.execute(
            "INSERT INTO watch_history(user_id,movie_id,movie_title,rating,watched_at,progress_seconds,duration_seconds) VALUES(?,?,?,?,?,?,?)",
            (user_id, str(movie_id), movie_title, rating, datetime.now().isoformat(), progress_seconds, duration_seconds)
        )
    conn.commit()

def get_watch_history(user_id):
    conn = get_db()
    return conn.execute(
        "SELECT movie_id,movie_title,rating,watched_at,progress_seconds,duration_seconds FROM watch_history WHERE user_id=? ORDER BY watched_at DESC",
        (user_id,)
    ).fetchall()

def get_watched_titles(user_id):
    conn = get_db()
    return [r[0] for r in conn.execute("SELECT movie_title FROM watch_history WHERE user_id=?", (user_id,)).fetchall()]

def get_movie_progress(user_id, movie_id):
    conn = get_db()
    row = conn.execute(
        "SELECT progress_seconds, duration_seconds FROM watch_history WHERE user_id=? AND movie_id=?",
        (user_id, str(movie_id))
    ).fetchone()
    return row if row else (0, 0)

# ── Friends activity ─────────────────────────────────────────
def get_friends_activity(limit=20):
    conn = get_db()
    return conn.execute("""
        SELECT u.username, w.movie_title, w.watched_at, w.movie_id
        FROM watch_history w
        JOIN users u ON w.user_id = u.id
        ORDER BY w.watched_at DESC
        LIMIT ?
    """, (limit,)).fetchall()

def save_chat(user_id, role, message):
    conn = get_db()
    conn.execute("INSERT INTO chat_history(user_id,role,message,timestamp) VALUES(?,?,?,?)",
                 (user_id, role, message, datetime.now().isoformat()))
    conn.commit()

def load_chat_from_db(user_id, limit=40):
    conn = get_db()
    rows = conn.execute(
        "SELECT role,message FROM chat_history WHERE user_id=? ORDER BY timestamp DESC LIMIT ?",
        (user_id, limit)
    ).fetchall()
    return [{"role": r[0], "content": r[1]} for r in reversed(rows)]

# ── TMDB ────────────────────────────────────────────────────
@st.cache_data(show_spinner=False, ttl=86400)
def fetch_poster(movie_id):
    try:
        data = requests.get(f"https://api.themoviedb.org/3/movie/{movie_id}?api_key={TMDB_API_KEY}", timeout=5).json()
        p = data.get("poster_path")
        return f"https://image.tmdb.org/t/p/w500{p}" if p else "https://via.placeholder.com/500x750?text=No+Poster"
    except: return "https://via.placeholder.com/500x750?text=No+Poster"

@st.cache_data(show_spinner=False, ttl=86400)
def fetch_movie_details(movie_id):
    try:
        data = requests.get(f"https://api.themoviedb.org/3/movie/{movie_id}?api_key={TMDB_API_KEY}", timeout=5).json()
        vids = requests.get(f"https://api.themoviedb.org/3/movie/{movie_id}/videos?api_key={TMDB_API_KEY}", timeout=5).json()
        trailer = next((f"https://www.youtube.com/watch?v={v['key']}" for v in vids.get("results", []) if v.get("type") == "Trailer" and v.get("site") == "YouTube"), None)
        return {
            "overview": data.get("overview", ""),
            "vote":     round(data.get("vote_average", 0), 1),
            "year":     data.get("release_date", "")[:4],
            "runtime":  data.get("runtime", 0),
            "trailer":  trailer,
            "genres":   ", ".join([g["name"] for g in data.get("genres", [])[:3]])
        }
    except: return {}

@st.cache_data(show_spinner=False, ttl=86400)
def search_tmdb_by_title(title):
    try:
        data = requests.get(f"https://api.themoviedb.org/3/search/movie?api_key={TMDB_API_KEY}&query={title}", timeout=5).json()
        results = data.get("results", [])
        return results[0] if results else None
    except: return None

# ── MODEL ───────────────────────────────────────────────────
@st.cache_resource
def load_model():
    if not os.path.exists("similarity.pkl"):
        try:
            import gdown
            gdown.download("https://drive.google.com/uc?id=1UBueaytEtkE4sRPdOt00neSctWQaAoWa", "similarity.pkl", quiet=False)
        except Exception as e:
            st.error(f"Could not download model: {e}"); st.stop()
    movies    = pickle.load(open("movies.pkl", "rb"))
    similarity= pickle.load(open("similarity.pkl", "rb"))
    return movies, similarity

def recommend(movie, user_id=None, top_n=10):
    movies, similarity = load_model()
    matches = movies[movies["title"] == movie]
    if matches.empty: return []
    idx = matches.index[0]
    raw = sorted(list(enumerate(similarity[idx])), reverse=True, key=lambda x: x[1])[1:top_n+30]
    watched = get_watched_titles(user_id) if user_id else []
    results = []
    for i, score in raw:
        title, m_id = movies.iloc[i].title, movies.iloc[i].movie_id
        if title not in watched:
            results.append({"title": title, "movie_id": m_id, "score": round(score*100, 1)})
        if len(results) == top_n: break
    return results

# ── GROQ ────────────────────────────────────────────────────
def ask_groq(api_history, user_message, watchlist_context="", movie_context=""):
    try:
        if _Groq is None: return "Groq library not installed."
        client = _Groq(api_key=GROQ_API_KEY)
        system_content = (
            "You are SceneSeeker AI, a friendly movie expert. "
            "Reply in the same language as the user (English/Urdu/Roman Urdu/Punjabi). "
            "When recommending movies, bold the title like **Movie Name**. "
            "Keep responses concise and engaging."
        )
        if movie_context:
            system_content += f"\n\nUser is currently watching: {movie_context}. Answer any questions about this movie — plot, ending, characters, trivia."
        if watchlist_context:
            system_content += f"\n\nUser's watch history: {watchlist_context}. Use this to personalize recommendations."
        response = _Groq(api_key=GROQ_API_KEY).chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=[{"role": "system", "content": system_content}] + api_history + [{"role": "user", "content": user_message}],
            max_tokens=1024, temperature=0.7
        )
        return response.choices[0].message.content
    except Exception as e: return f"Error: {str(e)}"

def extract_movie_titles(text):
    return re.findall(r'\*\*([^*]+)\*\*', text)

def time_ago(dt_str):
    try:
        dt   = datetime.fromisoformat(dt_str)
        diff = (datetime.now() - dt).total_seconds()
        if diff < 60:    return "just now"
        if diff < 3600:  return f"{int(diff//60)}m ago"
        if diff < 86400: return f"{int(diff//3600)}h ago"
        return f"{int(diff//86400)}d ago"
    except: return ""

# ── COMPONENTS ───────────────────────────────────────────────
def open_style_block():
    return """
    body { margin: 0; background: transparent; }
    .rec-grid { display: flex; gap: 12px; padding: 4px 2px 8px; overflow-x: auto; }
    .rec-card { position: relative; flex: 0 0 160px; border-radius: 10px; overflow: hidden; cursor: pointer; background: #111; }
    .rec-card img { width: 100%; height: 240px; object-fit: cover; display: block; border-radius: 10px; transition: transform 0.25s, filter 0.25s; }
    .rec-card:hover img { transform: scale(1.05); filter: brightness(0.35); }
    .rec-overlay { position: absolute; bottom: 0; left: 0; right: 0; padding: 50px 10px 14px; background: linear-gradient(to top, rgba(0,0,0,0.95) 60%, transparent); opacity: 0; transition: opacity 0.25s; }
    .rec-card:hover .rec-overlay { opacity: 1; }
    .rec-title { color: #fff; font-size: 12px; font-weight: 700; margin-bottom: 10px; text-align: center; font-family: Arial, sans-serif; line-height: 1.3; }
    .rec-btn { display: block; width: 100%; padding: 8px 0; border-radius: 6px; font-size: 12px; font-weight: 700; text-align: center; text-decoration: none; box-sizing: border-box; margin-bottom: 5px; }
    .rec-btn-watch { background: #e63946; color: #fff; font-family: Arial, sans-serif; }
    """

def render_rec_cards(results, user_id):
    cards_html = '<div class="rec-grid">'
    for movie in results:
        poster    = fetch_poster(movie["movie_id"])
        watch_url = f"https://www.vidking.net/embed/movie/{movie['movie_id']}?color=e63946&autoPlay=true"
        cards_html += f"""
        <div class="rec-card">
            <img src="{poster}" alt="{movie['title']}">
            <div class="rec-overlay">
                <div class="rec-title">{movie['title']}</div>
                <a href="{watch_url}" target="_blank" class="rec-btn rec-btn-watch">▶ Watch Now</a>
            </div>
        </div>"""
    cards_html += '</div>'
    components.html(cards_html + "<style>" + open_style_block() + "</style>", height=300, scrolling=False)

def render_player(movie_id, progress_seconds=0):
    url = f"https://www.vidking.net/embed/movie/{movie_id}?color=e63946&autoPlay=true"
    if progress_seconds > 30:
        url += f"&progress={progress_seconds}"
    
    # Attempt 2: Added ALL possible sandbox bypass flags for aggressive streaming embeds
    st.markdown(f"""
    <div style="margin:0.5rem 0; border-radius:12px; overflow:hidden;">
        <iframe src="{url}" width="100%" height="480"
            frameborder="0" allowfullscreen
            sandbox="allow-scripts allow-same-origin allow-presentation allow-forms allow-popups allow-popups-to-escape-sandbox allow-top-navigation-by-user-activation"
            allow="autoplay; fullscreen; encrypted-media; picture-in-picture">
        </iframe>
    </div>
    """, unsafe_allow_html=True)
    
    # The Fallback: A nice Streamlit button just in case the deployment platform blocks the iframe
    st.write("") # Thori si spacing ke liye
    st.link_button("🎥 Watch Movie in New Tab (If player doesn't load)", url, use_container_width=True)

def render_mini_movie_cards(titles):
    for j, title in enumerate(titles[:4]):
        result = search_tmdb_by_title(title)
        if not result: continue
        m_id = result.get("id")
        cols = st.columns(min(len(titles[:4]), 4))
        with cols[j]:
            st.image(fetch_poster(m_id), use_container_width=True)
            st.caption(title)
            details     = fetch_movie_details(m_id)
            trailer_url = details.get("trailer")
            watch_url   = f"https://www.vidking.net/embed/movie/{m_id}?color=e63946&autoPlay=true"
            b1, b2 = st.columns(2)
            b1.link_button("▶ Watch", watch_url, use_container_width=True)
            if trailer_url:
                b2.link_button("🎬", trailer_url, use_container_width=True)

# ── SIDEBAR: Friends Activity ────────────────────────────────
def render_friends_activity():
    with st.sidebar:
        st.markdown("### 👥 Friends Activity")
        activity = get_friends_activity(20)
        if not activity:
            st.caption("No activity yet — invite friends!")
            return
        current_user = st.session_state.get("username", "")
        html = '<div class="activity-feed">'
        for username, movie_title, watched_at, movie_id in activity:
            label   = "You" if username == current_user else username
            initial = label[0].upper()
            ago     = time_ago(watched_at)
            html += f"""
            <div class="activity-item">
                <div class="activity-avatar">{initial}</div>
                <div>
                    <div class="activity-text"><b>{label}</b> watched <b>{movie_title}</b></div>
                    <div class="activity-time">{ago}</div>
                </div>
            </div>"""
        html += '</div>'
        st.markdown(html, unsafe_allow_html=True)

# ── PAGES ───────────────────────────────────────────────────
def page_login():
    _, mid, _ = st.columns([1, 2, 1])
    with mid:
        st.markdown(f"<div style='text-align:center; padding:3rem 0 1rem;'>{logo(80)}<h2 style='margin-top:0.5rem'>{APP_NAME}</h2><p style='opacity:0.5'>Discover what your mood deserves</p></div>", unsafe_allow_html=True)
        name = st.text_input("Your name", placeholder="Type your name...", label_visibility="collapsed")
        if st.button("Start Exploring →", use_container_width=True, type="primary"):
            if name.strip():
                st.session_state.user_id  = get_or_create_user(name.strip())
                st.session_state.username = name.strip()
                st.rerun()
            else: st.warning("Enter your name!")

def page_discover():
    movies, _ = load_model()
    user_id   = st.session_state.get("user_id")
    selected  = st.selectbox("Pick a movie:", options=movies["title"].values, index=None, placeholder="Search movies...")
    if not selected: return

    row     = movies[movies["title"] == selected].iloc[0]
    details = fetch_movie_details(row.movie_id)
    poster  = fetch_poster(row.movie_id)

    # saved progress
    prog_sec, dur_sec = get_movie_progress(user_id, row.movie_id) if user_id else (0, 0)
    prog_pct = int((prog_sec / dur_sec) * 100) if dur_sec > 0 else 0

    c1, c2 = st.columns([1, 3])
    with c1: st.image(poster, use_container_width=True)
    with c2:
        st.markdown(f"### {selected}")
        meta = []
        if details.get('year'):    meta.append(f"📅 {details['year']}")
        if details.get('runtime'): meta.append(f"⏱ {details['runtime']} min")
        if details.get('vote'):    meta.append(f"⭐ {details['vote']}")
        if details.get('genres'):  meta.append(f"🎭 {details['genres']}")
        st.caption("  |  ".join(meta))
        st.write(details.get("overview", ""))

        # progress bar if partially watched
        if prog_pct > 0:
            st.markdown(f"""
            <div style="font-size:12px; opacity:0.6; margin-bottom:4px;">
                Continue from {prog_sec//60}m {prog_sec%60}s ({prog_pct}%)
            </div>
            <div class="progress-bar-outer">
                <div class="progress-bar-inner" style="width:{prog_pct}%"></div>
            </div>
            """, unsafe_allow_html=True)
            st.markdown("")

        col_w, col_t, col_ai, col_r = st.columns(4)
        with col_w:
            btn_label = "▶ Resume" if prog_pct > 0 else "▶ Watch Now"
            if st.button(btn_label, type="primary", use_container_width=True):
                st.session_state[f"watch_{row.movie_id}"] = not st.session_state.get(f"watch_{row.movie_id}", False)
                if st.session_state[f"watch_{row.movie_id}"] and user_id:
                    save_watch(user_id, row.movie_id, selected)
        with col_t:
            if details.get("trailer"):
                st.link_button("🎬 Trailer", details["trailer"], use_container_width=True)
        with col_ai:
            if st.button("🤖 Ask AI", use_container_width=True):
                # set movie context and switch tab via session
                st.session_state.movie_context = f"{selected} ({details.get('year', '')})"
                st.session_state.active_tab    = 1
                st.rerun()
        with col_r:
            if st.button("✦ Similar", use_container_width=True):
                st.session_state.last_results = recommend(selected, user_id=user_id)
                st.session_state.last_seed    = selected

    # inline player with resume
    if st.session_state.get(f"watch_{row.movie_id}", False):
        render_player(row.movie_id, progress_seconds=prog_sec)
        st.caption("💡 Progress auto-saves when you close the player")

    # recommendations
    if "last_results" in st.session_state and st.session_state.get("last_seed") == selected:
        st.markdown("#### You might also like")
        render_rec_cards(st.session_state.last_results[:8], user_id)

def page_ask_ai():
    user_id      = st.session_state.get("user_id")
    watched      = get_watched_titles(user_id) if user_id else []
    watchlist_ctx= ", ".join(watched[:10]) if watched else ""
    movie_ctx    = st.session_state.get("movie_context", "")

    if "chat_msgs" not in st.session_state:
        st.session_state.chat_msgs = load_chat_from_db(user_id) if user_id else []

    # movie context banner
    if movie_ctx:
        col_banner, col_clear = st.columns([5, 1])
        col_banner.info(f"🎬 Talking about: **{movie_ctx}**")
        if col_clear.button("✕ Clear"):
            st.session_state.movie_context = ""
            st.rerun()

    # suggestion chips — change based on context
    if movie_ctx:
        movie_name = movie_ctx.split("(")[0].strip()
        suggestions = [
            f"🔚 Explain the ending of {movie_name}",
            f"🎭 Who are the main characters in {movie_name}?",
            f"🏆 Is {movie_name} worth watching?",
            f"🎬 Movies similar to {movie_name}",
            f"🤔 What's the plot twist in {movie_name}?",
            f"⭐ Best scenes in {movie_name}",
        ]
    else:
        suggestions = [
            "🎬 Recommend me an action movie",
            "😂 Best comedies to watch tonight",
            "🧠 Mind-bending sci-fi films",
            "❤️ Romantic movies for the weekend",
            "🏆 Top rated movies of all time",
            "🎭 Based on my watchlist, what next?",
        ]

    st.markdown("**Quick questions:**")
    cols = st.columns(3)
    for i, s in enumerate(suggestions):
        if cols[i % 3].button(s, use_container_width=True, key=f"chip_{i}"):
            st.session_state._pending_prompt = s
    st.divider()

    # chat history
    for msg in st.session_state.chat_msgs:
        with st.chat_message(msg["role"]):
            st.write(msg["content"])
            if msg["role"] == "assistant":
                titles = extract_movie_titles(msg["content"])
                if titles: render_mini_movie_cards(titles)

    # input
    prompt = st.chat_input("Ask anything about movies...")
    if not prompt and hasattr(st.session_state, '_pending_prompt'):
        prompt = st.session_state._pending_prompt
        del st.session_state._pending_prompt

    if prompt:
        st.session_state.chat_msgs.append({"role": "user", "content": prompt})
        with st.chat_message("user"): st.write(prompt)
        with st.chat_message("assistant"):
            with st.spinner("Thinking..."):
                reply = ask_groq(
                    [{"role": m["role"], "content": m["content"]} for m in st.session_state.chat_msgs[:-1]],
                    prompt,
                    watchlist_context=watchlist_ctx,
                    movie_context=movie_ctx
                )
            st.write(reply)
            titles = extract_movie_titles(reply)
            if titles: render_mini_movie_cards(titles)
        st.session_state.chat_msgs.append({"role": "assistant", "content": reply})
        if user_id:
            save_chat(user_id, "user", prompt)
            save_chat(user_id, "assistant", reply)
        st.rerun()

def page_watchlist():
    user_id = st.session_state.get("user_id")
    history = get_watch_history(user_id)
    if not history:
        st.info("No films saved yet. Go discover something!"); return

    # continue watching — movies with progress
    in_progress = [(m_id, title, prog, dur) for m_id, title, _, _, prog, dur in history if prog and prog > 30]
    if in_progress:
        st.markdown("#### ⏸ Continue Watching")
        for m_id, title, prog, dur in in_progress[:5]:
            pct = int((prog/dur)*100) if dur else 0
            c1, c2 = st.columns([1, 6])
            with c1: st.image(fetch_poster(m_id), use_container_width=True)
            with c2:
                st.markdown(f"**{title}**")
                st.markdown(f"""
                <div class="progress-bar-outer">
                    <div class="progress-bar-inner" style="width:{pct}%"></div>
                </div>
                <div style="font-size:12px; opacity:0.5; margin-top:4px;">{prog//60}m {prog%60}s watched ({pct}%)</div>
                """, unsafe_allow_html=True)
                watch_url = f"https://www.vidking.net/embed/movie/{m_id}?color=e63946&autoPlay=true&progress={prog}"
                st.link_button("▶ Resume", watch_url)
        st.divider()

    st.markdown(f"#### 📋 All Watched ({len(history)} movies)")
    chunk_size = 5
    for i in range(0, min(len(history), 20), chunk_size):
        chunk = history[i:i+chunk_size]
        cols  = st.columns(chunk_size)
        for j, (m_id, title, rating, _, prog, dur) in enumerate(chunk):
            with cols[j]:
                st.image(fetch_poster(m_id), use_container_width=True)
                st.caption(title[:18])
                watch_url = f"https://www.vidking.net/embed/movie/{m_id}?color=e63946&autoPlay=true"
                st.link_button("▶", watch_url, use_container_width=True)

    st.divider()
    if history:
        last_title = history[0][1]
        recs = recommend(last_title, user_id=user_id, top_n=8)
        if recs:
            st.markdown(f"#### Because you watched **{last_title}**")
            render_rec_cards(recs, user_id)

# ── MAIN ────────────────────────────────────────────────────
def main():
    if "user_id" not in st.session_state:
        page_login(); return

    render_friends_activity()

    h1, h2, h3 = st.columns([2, 5, 2])
    h2.write(f"Welcome, **{st.session_state.username}**")
    if h3.button("Sign Out"): st.session_state.clear(); st.rerun()

    active = st.session_state.get("active_tab", 0)
    t1, t2, t3 = st.tabs(["🎬 Discover", "🤖 Ask AI", "📋 My Watchlist"])
    with t1: page_discover()
    with t2: page_ask_ai()
    with t3: page_watchlist()

if __name__ == "__main__": main()