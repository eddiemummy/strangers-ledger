# --------------------------------------------------------------
# 📚 The Stranger's Ledger (Personal Reading Tracker + LLM Recs)
# Admin-protected write; public read-only
# - Read / Reading / Favorite / Tags
# - Reading progress bar
# - Cover image upload
# - LLM recommendations from read books
# --------------------------------------------------------------

import streamlit as st
import os, re, json, uuid
from datetime import datetime
from typing import List, Dict, Any

# LLM (Gemini + LangChain)
from config import set_environment
from model import create_model
from langchain_core.messages.human import HumanMessage

# -----------------------------
# Environment & model
# -----------------------------
set_environment()
model = create_model()

# -----------------------------
# Simple "data store"
# -----------------------------
DATA_FILE = "books_db.json"
COVER_DIR = "covers"

os.makedirs(COVER_DIR, exist_ok=True)

def _load_db() -> List[Dict[str, Any]]:
    if os.path.exists(DATA_FILE):
        try:
            with open(DATA_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return []
    return []

def _save_db(data: List[Dict[str, Any]]):
    with open(DATA_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

def _slugify(text: str) -> str:
    s = re.sub(r"[^\w\s-]", "", text, flags=re.UNICODE).strip().lower()
    s = re.sub(r"[\s_-]+", "-", s)
    return s or str(uuid.uuid4())

def _find_by_id(db: List[Dict[str, Any]], bid: str):
    for x in db:
        if x["id"] == bid:
            return x
    return None

def _ensure_defaults(book: Dict[str, Any]) -> Dict[str, Any]:
    defaults = {
        "id": str(uuid.uuid4()),
        "title": "",
        "author": "",
        "status": "to_read",  # to_read | reading | read
        "progress": 0,        # 0..100
        "favorite": False,
        "tags": [],
        "cover_path": None,
        "rating": None,       # 1..10 optional
        "notes": "",
        "created_at": datetime.now().isoformat(timespec="seconds"),
        "updated_at": datetime.now().isoformat(timespec="seconds"),
    }
    merged = {**defaults, **book}
    merged["tags"] = sorted(list({t.strip() for t in merged.get("tags", []) if t.strip()}))
    merged["progress"] = max(0, min(100, int(merged.get("progress", 0) or 0)))
    if merged["progress"] >= 100:
        merged["status"] = "read"
    return merged

# -----------------------------
# UI
# -----------------------------
st.set_page_config(page_title="📚 The Stranger's Ledger", layout="wide")
st.title("📚 The Stranger's Ledger — Reading Tracker & Recommendations")

# -----------------------------
# Admin login / viewer mode
# -----------------------------
with st.sidebar:
    st.subheader("🔐 Admin Login")
    pwd = st.text_input("Password", type="password", placeholder="••••••••")
    login_btn = st.button("Login")

if "can_edit" not in st.session_state:
    st.session_state.can_edit = False

if login_btn:
    if pwd and pwd == st.secrets.get("ADMIN_PASS", ""):
        st.session_state.can_edit = True
        st.success("Admin mode enabled.")
    else:
        st.session_state.can_edit = False
        st.error("Wrong password.")

CAN_EDIT = st.session_state.can_edit

# -----------------------------
# Sidebar: totals & quick filters
# -----------------------------
db = _load_db()
total = len(db)
reading_cnt = sum(1 for x in db if x["status"] == "reading")
read_cnt = sum(1 for x in db if x["status"] == "read")
to_read_cnt = sum(1 for x in db if x["status"] == "to_read")

with st.sidebar:
    st.subheader("📊 Overview")
    st.metric("Total", total)
    st.metric("Reading", reading_cnt)
    st.metric("Read", read_cnt)
    st.metric("To Read", to_read_cnt)

    st.markdown("---")
    st.subheader("🔎 Quick Search")
    q = st.text_input("Search by Title/Author")
    tag_filter = st.text_input("Filter by tags (comma-separated)")
    fav_only = st.checkbox("Favorites only", value=False)
    status_pick = st.selectbox("Status", ["All", "to_read", "reading", "read"], index=0)

def _starbar(score: int | None) -> str:
    if score is None:
        return "—"
    score = max(0, min(10, int(score)))
    return "⭐" * score + "☆" * (10 - score)

def _book_card(book: Dict[str, Any]):
    cols = st.columns([1, 4, 2])
    with cols[0]:
        if book.get("cover_path") and os.path.exists(book["cover_path"]):
            st.image(book["cover_path"], use_column_width=True)
        else:
            st.write("**No cover**")
    with cols[1]:
        st.markdown(f"### {book['title']}")
        st.markdown(f"**Author:** {book['author'] or '-'}")
        st.markdown(f"**Status:** `{book['status']}`  |  **Progress:** {book['progress']}%")
        st.markdown(f"**Favorite:** {'❤️' if book.get('favorite') else '—'}")
        st.markdown(f"**Tags:** {', '.join(book.get('tags', [])) or '—'}")
        st.markdown(f"**Rating:** {_starbar(book.get('rating'))}")
        if book.get("notes"):
            with st.expander("Notes"):
                st.write(book["notes"])
    with cols[2]:
        st.caption(f"ID: `{book['id']}`")
        st.caption(f"Created: {book.get('created_at','-')}")
        st.caption(f"Updated: {book.get('updated_at','-')}")

# -----------------------------
# Tabs
# -----------------------------
tab_add, tab_reading, tab_library, tab_reco = st.tabs(
    ["➕ Add / Update Book", "📖 Currently Reading", "📚 Library", "✨ Recommendations"]
)

# =============================================================
# ➕ Add / Update Book
# =============================================================
with tab_add:
    st.subheader("Add a new book or update an existing one")

    if not CAN_EDIT:
        st.info("View-only mode. Login as admin to add or edit books.")
    else:
        book_ids = ["— new record —"] + [f"{b['title']} — {b['author']}  ({b['id']})" for b in db]
        pick = st.selectbox("Select a record to update", options=book_ids, index=0)
        selected_id = None
        if pick != "— new record —":
            m = re.search(r"\(([^)]+)\)$", pick)
            if m:
                selected_id = m.group(1)

        init = {}
        if selected_id:
            cur = _find_by_id(db, selected_id)
            if cur:
                init = cur.copy()

        with st.form("book_form", clear_on_submit=False):
            c1, c2 = st.columns([3, 2])
            with c1:
                title = st.text_input("Title", value=init.get("title", ""))
                author = st.text_input("Author", value=init.get("author", ""))
                status = st.selectbox(
                    "Status",
                    options=["to_read", "reading", "read"],
                    index=["to_read", "reading", "read"].index(init.get("status", "to_read")),
                )
                progress = st.slider("Progress (%)", min_value=0, max_value=100, value=int(init.get("progress", 0)))
                favorite = st.checkbox("Favorite", value=bool(init.get("favorite", False)))
                rating = st.number_input("Rating (1–10, optional)", min_value=1, max_value=10, value=int(init.get("rating") or 7))
                tags = st.text_input("Tags (comma-separated)", value=",".join(init.get("tags", [])))
                notes = st.text_area("Notes", value=init.get("notes", ""), height=100)
            with c2:
                cover_file = st.file_uploader("Upload Cover (jpg/png)", type=["jpg", "jpeg", "png"])
                if init.get("cover_path") and os.path.exists(init["cover_path"]):
                    st.image(init["cover_path"], caption="Current cover", use_column_width=True)
                    if st.checkbox("Remove current cover"):
                        try:
                            os.remove(init["cover_path"])
                        except Exception:
                            pass
                        init["cover_path"] = None

            submitted = st.form_submit_button("Save")
            if submitted:
                if not title.strip():
                    st.error("Title is required.")
                else:
                    book = {
                        "id": init.get("id", str(uuid.uuid4())),
                        "title": title.strip(),
                        "author": author.strip(),
                        "status": status,
                        "progress": progress,
                        "favorite": favorite,
                        "rating": rating if rating else None,
                        "tags": [t.strip() for t in tags.split(",") if t.strip()],
                        "notes": notes.strip(),
                        "updated_at": datetime.now().isoformat(timespec="seconds"),
                    }

                    if cover_file is not None:
                        ext = os.path.splitext(cover_file.name)[1].lower()
                        fname = f"{_slugify(title)}-{uuid.uuid4().hex}{ext}"
                        save_path = os.path.join(COVER_DIR, fname)
                        with open(save_path, "wb") as f:
                            f.write(cover_file.read())
                        book["cover_path"] = save_path
                    else:
                        if init.get("cover_path"):
                            book["cover_path"] = init["cover_path"]

                    if book["progress"] >= 100:
                        book["status"] = "read"

                    if selected_id:
                        for i, b in enumerate(db):
                            if b["id"] == selected_id:
                                db[i] = _ensure_defaults({**b, **book})
                                break
                        st.success("Record updated ✅")
                    else:
                        db.append(_ensure_defaults(book))
                        st.success("New book added ✅")

                    _save_db(db)

# =============================================================
# 📖 Currently Reading (update progress)
# =============================================================
with tab_reading:
    st.subheader("Currently Reading")
    reading = [b for b in db if b["status"] == "reading"]
    if not reading:
        st.info("No books are marked as 'reading'. Use the Add/Update tab to set one.")
    else:
        for b in reading:
            st.markdown(f"### {b['title']} — {b['author'] or ''}")
            cols = st.columns([4, 1])
            with cols[0]:
                new_prog = st.slider(f"Progress (%) — {b['id']}", 0, 100, b["progress"], key=f"prog_{b['id']}")
            with cols[1]:
                if CAN_EDIT and st.button("Update", key=f"upd_{b['id']}"):
                    b["progress"] = int(new_prog)
                    if b["progress"] >= 100:
                        b["status"] = "read"
                    b["updated_at"] = datetime.now().isoformat(timespec="seconds")
                    _save_db(db)
                    st.success("Updated!")
                elif not CAN_EDIT:
                    st.caption("Login as admin to update.")

            if b.get("cover_path") and os.path.exists(b["cover_path"]):
                st.image(b["cover_path"], width=160)
            st.progress(b["progress"] / 100)
            st.markdown("---")

# =============================================================
# 📚 Library (list, filter, quick edit)
# =============================================================
with tab_library:
    st.subheader("Library")
    filtered = db[:]
    if q:
        qlow = q.strip().lower()
        filtered = [b for b in filtered if qlow in b["title"].lower() or qlow in (b["author"] or "").lower()]
    if tag_filter.strip():
        wanted = {t.strip().lower() for t in tag_filter.split(",") if t.strip()}
        filtered = [b for b in filtered if wanted.issubset({t.lower() for t in b.get("tags", [])})]
    if fav_only:
        filtered = [b for b in filtered if b.get("favorite")]
    if status_pick != "All":
        filtered = [b for b in filtered if b["status"] == status_pick]

    if not filtered:
        st.info("No results for these filters.")
    else:
        for b in filtered:
            # Card
            cols_top = st.columns([6, 2])
            with cols_top[0]:
                colA, colB = st.columns([1, 3])
                with colA:
                    if b.get("cover_path") and os.path.exists(b["cover_path"]):
                        st.image(b["cover_path"], width=120)
                    else:
                        st.write("**No cover**")
                with colB:
                    st.markdown(f"### {b['title']}")
                    st.markdown(f"**Author:** {b['author'] or '-'}")
                    st.markdown(f"**Status:** `{b['status']}`  |  **Progress:** {b['progress']}%")
                    st.markdown(f"**Favorite:** {'❤️' if b.get('favorite') else '—'}")
                    st.markdown(f"**Tags:** {', '.join(b.get('tags', [])) or '—'}")
                    st.markdown(f"**Rating:** {_starbar(b.get('rating'))}")
                    if b.get("notes"):
                        with st.expander("Notes"):
                            st.write(b["notes"])
            with cols_top[1]:
                st.caption(f"ID: `{b['id']}`")
                st.caption(f"Created: {b.get('created_at','-')}")
                st.caption(f"Updated: {b.get('updated_at','-')}")

            with st.expander("Quick Edit"):
                col1, col2, col3, col4 = st.columns(4)
                with col1:
                    new_fav = st.checkbox("Favorite", value=b.get("favorite", False), key=f"fav_{b['id']}", disabled=not CAN_EDIT)
                with col2:
                    new_status = st.selectbox(
                        "Status", ["to_read", "reading", "read"],
                        index=["to_read","reading","read"].index(b["status"]),
                        key=f"st_{b['id']}",
                        disabled=not CAN_EDIT
                    )
                with col3:
                    new_rating = st.number_input(
                        "Rating (1–10)", min_value=1, max_value=10,
                        value=int(b.get("rating") or 7), key=f"rt_{b['id']}",
                        disabled=not CAN_EDIT
                    )
                with col4:
                    new_tags = st.text_input(
                        "Tags (comma-separated)", value=",".join(b.get("tags", [])),
                        key=f"tg_{b['id']}", disabled=not CAN_EDIT
                    )

                colE, colF = st.columns(2)
                with colE:
                    if CAN_EDIT and st.button("Save", key=f"quicksave_{b['id']}"):
                        b["favorite"] = bool(new_fav)
                        b["status"] = new_status
                        b["rating"] = int(new_rating) if new_rating else None
                        b["tags"] = [t.strip() for t in new_tags.split(",") if t.strip()]
                        b["updated_at"] = datetime.now().isoformat(timespec="seconds")
                        _save_db(db)
                        st.success("Saved.")
                    elif not CAN_EDIT:
                        st.caption("Login as admin to save.")
                with colF:
                    if CAN_EDIT and st.button("Delete", key=f"del_{b['id']}"):
                        if b.get("cover_path") and os.path.exists(b["cover_path"]):
                            try:
                                os.remove(b["cover_path"])
                            except Exception:
                                pass
                        db.remove(b)
                        _save_db(db)
                        st.warning("Deleted.")
                        st.experimental_rerun()
                    elif not CAN_EDIT:
                        st.caption("Login as admin to delete.")

            st.markdown("---")

# =============================================================
# ✨ Recommendations (LLM from read books)
# =============================================================
with tab_reco:
    st.subheader("LLM Recommendations from Read Books")
    read_books = [b for b in db if b["status"] == "read"]
    if not read_books:
        st.info("Add some books marked as 'read' to get recommendations.")
    else:
        st.write(f"Found **{len(read_books)}** read books.")
        seed_lines = []
        for b in read_books[:40]:
            tags = ", ".join(b.get("tags", []))
            seed_lines.append(f"- {b['title']} — {b.get('author','?')}  [tags: {tags}]  [fav:{'yes' if b.get('favorite') else 'no'}]  [rating:{b.get('rating') or '-'}]")

        st.markdown("**Seed List (summary):**")
        st.code("\n".join(seed_lines), language="markdown")

        want_n = st.slider("Number of recommendations", 5, 15, 10)
        focus_tags = st.text_input("Prioritize tags (comma-separated, optional)")
        only_favs = st.checkbox("Draw inspiration from favorites only", value=True)

        if st.button("🪄 Generate Recommendations"):
            focus_txt = f"Priority tags: {focus_tags}" if focus_tags.strip() else "Priority: flexible"
            seeds = [s for s in seed_lines if (("fav:yes" in s) if only_favs else True)]
            prompt = f"""
You are a seasoned literary curator. Based on the following 'read' books,
recommend **{want_n}** new books for the user.
For each recommendation, include briefly:
- **Title — Author**
- Why recommended? (1–2 sentences)
- Related themes / atmosphere
- Reading Difficulty: X/10

{focus_txt}

Summary of read books:
{chr(10).join(seeds)}

Rules:
- Answer in English.
- Avoid recommending many works by the same author consecutively.
- Strive for diversity (country/period/theme).
"""
            with st.spinner("Generating recommendations..."):
                try:
                    resp = model.invoke([HumanMessage(content=prompt)])
                    out = resp.content
                    st.markdown("### Recommendations")
                    st.markdown(out)

                    if CAN_EDIT and st.button("💾 Save Recommendations"):
                        with open("reading_recommendations.txt", "a", encoding="utf-8") as f:
                            f.write(f"\n===== {datetime.now().isoformat(timespec='seconds')} =====\n{out}\n")
                        st.success("Recommendations saved.")
                    elif not CAN_EDIT:
                        st.caption("Login as admin to save recommendations.")
                except Exception as e:
                    st.error(f"Error: {e}")

# --------------------------------------------------------------
# Footer
# --------------------------------------------------------------
st.markdown("---")
st.caption("📚 Crafted by a Reader-Friendly LLM Assistant — The Stranger's Ledger")
