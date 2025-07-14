import streamlit as st
import praw
import os
from dotenv import load_dotenv
from groq import Groq
from datetime import datetime
import requests
import time

# === Session State Initialization ===
if "persona" not in st.session_state:
    st.session_state.persona = None
if "username" not in st.session_state:
    st.session_state.username = None
if "profile_info" not in st.session_state:
    st.session_state.profile_info = None
if "dark_mode" not in st.session_state:
    st.session_state.dark_mode = True

# === Load credentials ===
load_dotenv()
REDDIT_CLIENT_ID = os.getenv("REDDIT_CLIENT_ID")
REDDIT_CLIENT_SECRET = os.getenv("REDDIT_CLIENT_SECRET")
REDDIT_USER_AGENT = os.getenv("REDDIT_USER_AGENT")
GROQ_API_KEY = os.getenv("GROQ_API_KEY")

# === Init APIs ===
reddit = praw.Reddit(
    client_id=REDDIT_CLIENT_ID,
    client_secret=REDDIT_CLIENT_SECRET,
    user_agent=REDDIT_USER_AGENT
)
groq_client = Groq(api_key=GROQ_API_KEY)

st.set_page_config(page_title="🧠 Reddit Persona Generator", layout="wide")

# === Sidebar for theme toggle ===
st.sidebar.markdown("## 🌃 Theme")
dark_mode_toggle = st.sidebar.toggle("Enable Dark Mode", value=st.session_state.dark_mode)
st.session_state.dark_mode = dark_mode_toggle

# === Apply Theme CSS ===
if st.session_state.dark_mode:
    st.markdown("""
        <style>
            @import url('https://fonts.googleapis.com/css2?family=Orbitron:wght@500&display=swap');
            body { background-color: #0d0d0d; color: white; font-family: 'Orbitron', sans-serif; }
            .neon-box {
                background-color: #0d0d0d;
                color: #39ff14;
                font-family: monospace;
                padding: 20px;
                border-radius: 10px;
                border: 1px solid #39ff14;
                white-space: pre-wrap;
                overflow-x: auto;
            }
            input, textarea, .stButton > button {
                color: white;
            }
            .stButton > button {
                border: 1px solid #39ff14;
                background: transparent;
                color: #39ff14;
                transition: 0.3s ease;
            }
            .stButton > button:hover {
                background-color: #39ff14;
                color: black;
                transform: scale(1.05);
            }
            .profile-text p, .profile-text h3 {
                color: #ffffff !important;
            }
        </style>
    """, unsafe_allow_html=True)
else:
    st.markdown("""
        <style>
            body { background-color: #ffffff; color: black; font-family: 'Orbitron', sans-serif; }
            .neon-box {
                background-color: #ffffff;
                color: #000000;
                font-family: monospace;
                padding: 20px;
                border-radius: 10px;
                border: 1px solid #ccc;
                white-space: pre-wrap;
                overflow-x: auto;
            }
            input, textarea, .stButton > button {
                color: black;
            }
        </style>
    """, unsafe_allow_html=True)

# === Helper Functions ===
def extract_username(url: str) -> str:
    if not url.startswith("https://www.reddit.com/user/"):
        raise ValueError("Invalid Reddit profile URL.")
    return url.rstrip("/").split("/")[-1]

def fetch_user_data(username: str, limit=30):
    user = reddit.redditor(username)
    posts, comments = [], []
    profile_info = {}
    try:
        profile_info = {
            "name": user.name,
            "icon_img": user.icon_img,
            "karma": user.link_karma + user.comment_karma,
            "cake_day": datetime.utcfromtimestamp(user.created_utc).strftime('%Y-%m-%d')
        }
        for post in user.submissions.new(limit=limit):
            posts.append({
                "title": post.title,
                "body": post.selftext,
                "url": f"https://reddit.com{post.permalink}"
            })
        for comment in user.comments.new(limit=limit):
            comments.append({
                "body": comment.body,
                "url": f"https://reddit.com{comment.permalink}"
            })
    except Exception as e:
        st.error(f"❌ Failed to fetch user data: {e}")
    return posts, comments, profile_info

def summarize_chunks(title, entries, chunk_size=5):
    summaries = []
    for i in range(0, len(entries), chunk_size):
        chunk = entries[i:i+chunk_size]
        content = "\n\n".join([
            f"Title: {x['title']}\n{x['body']}" if 'title' in x else x['body']
            for x in chunk
        ])
        prompt = f"Summarize the following Reddit {title} to capture the author's key personality traits and behavior:\n\n{content}"
        success = False
        while not success:
            try:
                response = groq_client.chat.completions.create(
                    model="llama3-70b-8192",
                    messages=[{"role": "user", "content": prompt}],
                    temperature=0.3
                )
                if response.choices and response.choices[0].message:
                    summaries.append(response.choices[0].message.content.strip())
                else:
                    summaries.append("[Summary failed]")
                success = True
            except Exception as e:
                if "rate limit" in str(e).lower():
                    st.warning("⏳ Rate limit hit. Waiting 10 seconds...")
                    time.sleep(10)
                else:
                    summaries.append("[Summary failed]")
                    st.warning(f"⚠️ Summarization chunk failed: {e}")
                    success = True
    return summaries

def build_prompt(post_summaries, comment_summaries, urls):
    prompt = (
        "You're an expert in behavior analysis. Based on the Reddit summaries below, create a full user persona in the following format:\n\n"
        "👤 Basic Info\n- Age\n- Occupation\n- Status\n- Location\n- Tier\n- Archetype\n\n"
        "🧠 Tags: Practical, Adaptable, Active, Spontaneous\n"
        "Personality Spectrum:\n- Introvert–Extrovert\n- Intuition–Sensing\n- Feeling–Thinking\n- Perceiving–Judging\n\n"
        "🔥 Motivations (use bars like ▓▓▓░░):\n- Convenience\n- Wellness\n- Speed\n- Preferences\n- Comfort\n- Dietary Needs\n\n"
        "💬 Behaviour & Habits\n😤 Frustrations\n🎯 Goals & Needs\n\n"
        "⚠️ Cite the source Reddit URL next to each insight.\n\n"
    )
    for i, s in enumerate(post_summaries):
        prompt += f"📌 Post Summary {i+1}:\n{s}\nURL: {urls[i]}\n\n"
    for j, s in enumerate(comment_summaries):
        index = len(post_summaries) + j
        if index < len(urls):
            prompt += f"💬 Comment Summary {j+1}:\n{s}\nURL: {urls[index]}\n\n"
    return prompt

def generate_persona(prompt):
    try:
        response = groq_client.chat.completions.create(
            model="llama3-70b-8192",
            messages=[{"role": "user", "content": prompt}],
            temperature=0.7
        )
        if response.choices and response.choices[0].message:
            return response.choices[0].message.content
        else:
            return "❌ No content returned by model."
    except Exception as e:
        return f"❌ LLM Error: {e}"

def save_persona(username, content):
    os.makedirs("outputs", exist_ok=True)
    path = f"outputs/{username}_persona.txt"
    with open(path, "w", encoding="utf-8") as f:
        f.write(content)
    return path

# === UI Layout ===
col1, col2 = st.columns([1, 2])

with col1:
    st.markdown("## 🔗 Input")
    st.image("https://cdn-icons-png.flaticon.com/512/4712/4712109.png", width=80)
    st.markdown("**🤖 I’m your Reddit Persona Bot! Paste a profile URL and I’ll analyze it for you.**")
    profile_url = st.text_input("Reddit Profile URL", placeholder="https://www.reddit.com/user/example/")
    generate = st.button("Generate Persona")

if generate and profile_url:
    try:
        username = extract_username(profile_url)
        posts, comments, profile_info = fetch_user_data(username, limit=30)
        if not posts and not comments:
            st.warning("❌ No posts or comments found.")
        else:
            with st.spinner("⏳ Summarizing Reddit activity..."):
                post_summaries = summarize_chunks("posts", posts)
                comment_summaries = summarize_chunks("comments", comments)
                all_urls = [p["url"] for p in posts] + [c["url"] for c in comments]

            if not post_summaries and not comment_summaries:
                st.warning("❌ Not enough content to build a persona.")
                st.stop()

            with st.spinner("🧠 Generating Persona using LLM..."):
                prompt = build_prompt(post_summaries, comment_summaries, all_urls)
                persona = generate_persona(prompt)
                save_persona(username, persona)

            # Save to session state
            st.session_state.persona = persona
            st.session_state.username = username
            st.session_state.profile_info = profile_info

    except Exception as e:
        st.error(f"❌ Error: {e}")

# === Show Output After Generation ===
if st.session_state.persona and st.session_state.username:
    with col2:
        st.markdown("## 👤 Reddit Profile")
        if st.session_state.profile_info.get("icon_img"):
            st.markdown(f"""
                <div style='background:#111;padding:15px;border-radius:10px;border:1px solid #39ff14;display:flex;align-items:center'>
                    <img src="{st.session_state.profile_info['icon_img']}" width="80" style="border-radius:50%;margin-right:15px"/>
                    <div class="profile-text">
                        <h3 style="margin:0">u/{st.session_state.profile_info['name']}</h3>
                        <p style="margin:0">Karma: {st.session_state.profile_info['karma']}</p>
                        <p style="margin:0">Cake Day: {st.session_state.profile_info['cake_day']}</p>
                    </div>
                </div>
            """, unsafe_allow_html=True)
        st.markdown("---")
        st.markdown("## 🧠 Persona Output")
        st.markdown(f'<div class="neon-box">{st.session_state.persona}</div>', unsafe_allow_html=True)
        st.download_button(
            "📄 Download Persona (Text)",
            data=st.session_state.persona,
            file_name=f"{st.session_state.username}_persona.txt",
            mime="text/plain"
        )
