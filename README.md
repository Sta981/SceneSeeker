# SceneSeeker

An AI-powered movie discovery and streaming platform built with Python and Streamlit. SceneSeeker combines content-based recommendation, a conversational AI assistant, and an embedded video player to deliver a personalized cinema experience.

---

## Features

**Movie Discovery**
- Search across 5,000+ movies powered by a cosine similarity recommendation model
- View movie details including runtime, genre, rating, and overview fetched live from TMDB
- Watch movies inline via the VidKing embedded player with autoplay and brand color theming
- Resume playback from where you left off using saved progress timestamps
- One-click trailer access via YouTube

**AI Recommendations**
- Content-based filtering using TF-IDF vectorization and cosine similarity
- Filters out already-watched titles from recommendations automatically
- Recommendations update based on each user's personal watch history

**Ask AI**
- Conversational movie assistant powered by LLaMA 3.3 70B via Groq API
- Context-aware: when watching a movie, the AI automatically answers questions about that specific film (plot, ending, characters, trivia)
- Supports English, Urdu, Roman Urdu, and Punjabi
- Quick suggestion chips for common queries
- Movie cards with Watch and Trailer buttons rendered inline when AI recommends titles

**Friends Activity Feed**
- Sidebar feed showing all users' recent watch activity in real time
- Pulls from shared SQLite database — no extra backend required

**Watchlist**
- Poster grid of all watched movies with direct resume links
- Continue Watching section showing in-progress movies with visual progress bars
- Automatic recommendations based on the most recently watched title

---

## Tech Stack

| Layer | Technology |
|---|---|
| Frontend | Streamlit |
| Recommendation Model | Scikit-learn (TF-IDF, Cosine Similarity) |
| AI Assistant | Groq API (LLaMA 3.3 70B) |
| Movie Data | TMDB API |
| Video Player | VidKing Embed API |
| Database | SQLite (via Python sqlite3) |
| Language | Python 3.9+ |

---

## Project Structure

```
SceneSeeker/
├── app.py                        # Main application — all pages and logic
├── movies.pkl                    # Preprocessed movie dataset
├── similarity.pkl                # Cosine similarity matrix (auto-downloaded if missing)
├── sceneseeker.db                # SQLite database (auto-created on first run)
├── movie-recomender-system.ipynb # Data preprocessing and model training notebook
├── .streamlit/
│   └── secrets.toml              # API keys (not committed to version control)
├── requirements.txt
├── Procfile
└── setup.sh
```

---

## Setup and Installation

**Requirements:** Python 3.9+, pip

**Step 1 — Clone the repository**

```bash
git clone https://github.com/Sta981/SceneSeeker.git
cd SceneSeeker
```

**Step 2 — Install dependencies**

```bash
pip install -r requirements.txt
```

**Step 3 — Configure API keys**

Create `.streamlit/secrets.toml`:

```toml
GROQ_API_KEY = "your_groq_api_key"
TMDB_API_KEY = "your_tmdb_api_key"
```

Get keys from:
- Groq: https://console.groq.com
- TMDB: https://www.themoviedb.org/settings/api

**Step 4 — Run the application**

```bash
streamlit run app.py
```

App runs at `http://localhost:8501`

Note: `similarity.pkl` is large and not included in the repository. It downloads automatically from Google Drive on first run via `gdown`.

---

## Deployment

This project is configured for Streamlit Community Cloud.

1. Push repository to GitHub (ensure `secrets.toml` is in `.gitignore`)
2. Go to https://share.streamlit.io and connect your GitHub account
3. Select repository `Sta981/SceneSeeker`, branch `main`, file `app.py`
4. Under Advanced Settings, add secrets:

```toml
GROQ_API_KEY = "your_groq_api_key"
TMDB_API_KEY = "your_tmdb_api_key"
```

5. Click Deploy

---

## Database Schema

| Table | Purpose |
|---|---|
| users | Stores username and registration timestamp |
| watch_history | Tracks watched movies, ratings, and playback progress per user |
| chat_history | Persists AI chat messages per user across sessions |

---

## How the Recommendation Model Works

1. Movie metadata (genres, keywords, cast, crew, overview) was combined into a single text field per movie
2. TF-IDF vectorization converts text to numerical vectors
3. Cosine similarity matrix computed across all 5,000 movies
4. At runtime, the top similar movies are retrieved for any selected title
5. Already-watched titles are excluded from results for each user

---

## Dependencies

| Package | Purpose |
|---|---|
| streamlit | Web application framework |
| scikit-learn | TF-IDF vectorizer and cosine similarity |
| groq | LLaMA 3.3 70B API client |
| requests | TMDB API calls |
| pandas | Data manipulation |
| pickle | Model serialization |
| gdown | Google Drive model download |
| Pillow | Favicon generation |

---

*Developed by Syed Tahir — BS Artificial Intelligence, 4th Semester, Superior University Lahore*
