import base64
import json
import time
from pathlib import Path

import streamlit as st
import streamlit.components.v1 as components

APP_DIR = Path(__file__).parent
DATA_DIR = APP_DIR / "data"
SAMPLE_BANK_PATH = DATA_DIR / "sample_questions.json"

st.set_page_config(page_title="GATE PYQ Practice", page_icon="📝", layout="wide")

st.markdown("""
<style>
.block-container {padding-top: 1.5rem; max-width: 1200px;}
.question-card {padding: 1rem 1.2rem; border: 1px solid rgba(128,128,128,.35); border-radius: 12px; margin: .5rem 0 1rem 0;}
.small-muted {color: #777; font-size: .9rem;}
</style>
""", unsafe_allow_html=True)

st.title("📝 GATE PYQ Practice")
st.caption("A starter app for practising previous-year GATE papers under timed conditions.")

def load_sample_bank():
    with open(SAMPLE_BANK_PATH, "r", encoding="utf-8") as f:
        return json.load(f)

def normalize_bank(raw):
    """Accept either {'questions': [...]} or a list of question objects."""
    if isinstance(raw, list):
        questions = raw
        meta = {}
    elif isinstance(raw, dict) and isinstance(raw.get("questions"), list):
        questions = raw["questions"]
        meta = raw
    else:
        raise ValueError("JSON must be a list of questions or an object containing a 'questions' list.")

    cleaned = []
    for i, q in enumerate(questions, start=1):
        if not isinstance(q, dict) or "question" not in q:
            raise ValueError(f"Question {i} must be an object with a 'question' field.")
        qtype = str(q.get("type", "MCQ")).upper()
        if qtype not in ("MCQ", "MSQ", "NAT"):
            raise ValueError(f"Question {i}: type must be MCQ, MSQ, or NAT.")
        item = {
            "id": str(q.get("id", i)),
            "question": str(q["question"]),
            "type": qtype,
            "options": q.get("options", {}) if qtype != "NAT" else {},
            "answer": q.get("answer"),
            "marks": float(q.get("marks", 1)),
            "negative_marks": float(q.get("negative_marks", 0.33 if qtype == "MCQ" else 0)),
            "explanation": str(q.get("explanation", "")),
            "subject": str(q.get("subject", "Uncategorized")),
        }
        if qtype in ("MCQ", "MSQ") and not isinstance(item["options"], dict):
            raise ValueError(f"Question {i}: options must be an object, e.g. {{'A':'...', 'B':'...'}}.")
        cleaned.append(item)
    if not cleaned:
        raise ValueError("The question bank is empty.")
    return {"title": str(meta.get("title", "Uploaded question bank")), "questions": cleaned}

def render_pdf(pdf_bytes):
    encoded = base64.b64encode(pdf_bytes).decode("utf-8")
    pdf_html = f"""
    <iframe src="data:application/pdf;base64,{encoded}"
      width="100%" height="760px" style="border:1px solid #aaa;border-radius:8px"
      title="Uploaded GATE question paper"></iframe>
    """
    components.html(pdf_html, height=780, scrolling=True)

def reset_attempt(questions, duration_minutes, paper_title):
    st.session_state.attempt = {
        "questions": questions,
        "answers": {},
        "marked": set(),
        "index": 0,
        "start_time": time.time(),
        "duration_seconds": int(duration_minutes * 60),
        "submitted": False,
        "paper_title": paper_title,
    }

def calculate_results(attempt):
    correct = 0.0
    attempted = 0
    correct_count = 0
    wrong_count = 0
    unattempted = 0
    per_subject = {}
    for q in attempt["questions"]:
        qid = q["id"]
        user_answer = attempt["answers"].get(qid)
        expected = q.get("answer")
        subject = q.get("subject", "Uncategorized")
        stats = per_subject.setdefault(subject, {"correct": 0, "wrong": 0, "unattempted": 0, "marks": 0.0})
        if user_answer is None or user_answer == "" or user_answer == []:
            unattempted += 1
            stats["unattempted"] += 1
            continue
        attempted += 1
        is_correct = False
        if q["type"] == "NAT":
            try:
                tolerance = float(q.get("tolerance", 0.0))
                is_correct = abs(float(user_answer) - float(expected)) <= tolerance
            except (ValueError, TypeError):
                is_correct = False
        elif q["type"] == "MSQ":
            is_correct = set(user_answer) == set(expected if isinstance(expected, list) else [expected])
        else:
            is_correct = str(user_answer) == str(expected)
        if is_correct:
            correct_count += 1
            correct += q["marks"]
            stats["correct"] += 1
            stats["marks"] += q["marks"]
        else:
            wrong_count += 1
            penalty = q["negative_marks"] if q["type"] == "MCQ" else 0
            correct -= penalty
            stats["wrong"] += 1
            stats["marks"] -= penalty
    return {
        "score": correct,
        "attempted": attempted,
        "correct_count": correct_count,
        "wrong_count": wrong_count,
        "unattempted": unattempted,
        "accuracy": (correct_count / attempted * 100) if attempted else 0,
        "per_subject": per_subject,
    }

# Sidebar: select mode and configure test
st.sidebar.header("Test setup")
mode = st.sidebar.radio("Choose mode", ["Interactive test", "Original PDF + timer"], index=0)
year = st.sidebar.selectbox("Paper year", ["2025", "2024", "2023", "2022", "2021", "2020", "2019", "Older / other"], index=0)
paper = st.sidebar.selectbox("Paper", ["GATE CSE", "GATE DA", "Other"], index=0)
duration = st.sidebar.number_input("Duration (minutes)", min_value=1, max_value=240, value=180, step=5)
st.sidebar.caption("You can change the duration for practice. Official paper duration is commonly 180 minutes; check the selected paper's instructions.")

if mode == "Original PDF + timer":
    st.subheader("Original PDF practice")
    st.write("Upload a question paper PDF. The timer runs separately; keep this tab open while you attempt the paper.")
    uploaded_pdf = st.file_uploader("Upload question paper PDF", type=["pdf"], key="pdf_upload")
    if uploaded_pdf:
        col1, col2 = st.columns([3, 1])
        with col1:
            st.write(f"**Selected:** {uploaded_pdf.name}")
        with col2:
            if st.button("Start / restart timer", type="primary", use_container_width=True):
                st.session_state.pdf_timer_start = time.time()
                st.session_state.pdf_timer_duration = int(duration * 60)
                st.session_state.pdf_timer_submitted = False
        if "pdf_timer_start" in st.session_state:
            elapsed = int(time.time() - st.session_state.pdf_timer_start)
            remaining = max(0, st.session_state.pdf_timer_duration - elapsed)
            mins, secs = divmod(remaining, 60)
            st.metric("Time remaining", f"{mins:02d}:{secs:02d}")
            if remaining == 0:
                st.warning("Time is up. Submit/finish your attempt.")
            else:
                st.caption("The countdown refreshes when you interact with the page. For a more accurate visible countdown, keep the timer panel open.")
        render_pdf(uploaded_pdf.getvalue())
        st.info("This mode displays the source PDF. It does not automatically grade answers. Use Interactive test mode for automatic marking.")
    else:
        st.info("Upload a PDF to begin. For best results, use a text-based PDF rather than a scanned image.")
else:
    st.subheader("Interactive test")
    st.write("For this first version, questions are loaded from a structured JSON question bank. You can use the sample bank or upload your own.")
    source = st.radio("Question source", ["Sample questions", "Upload question-bank JSON"], horizontal=True)
    bank = None
    if source == "Sample questions":
        try:
            bank = normalize_bank(load_sample_bank())
        except Exception as exc:
            st.error(f"Could not load sample bank: {exc}")
    else:
        json_file = st.file_uploader("Upload question bank (.json)", type=["json"], key="json_upload")
        if json_file:
            try:
                bank = normalize_bank(json.load(json_file))
            except Exception as exc:
                st.error(f"Could not read question bank: {exc}")

    if bank:
        title = st.text_input("Test title", value=f"GATE {paper.replace('GATE ', '')} {year} practice")
        if "attempt" not in st.session_state or st.session_state.get("attempt", {}).get("paper_title") != title:
            st.session_state.pop("attempt", None)
        if st.button("Start new test", type="primary"):
            reset_attempt(bank["questions"], duration, title)
            st.rerun()

        attempt = st.session_state.get("attempt")
        if attempt:
            # Keep the bank frozen for this attempt.
            if not attempt["submitted"] and time.time() - attempt["start_time"] >= attempt["duration_seconds"]:
                attempt["submitted"] = True
                attempt["auto_submitted"] = True

            if attempt["submitted"]:
                result = calculate_results(attempt)
                st.success("Test submitted automatically because time expired." if attempt.get("auto_submitted") else "Test submitted.")
                a, b, c, d = st.columns(4)
                a.metric("Score", f"{result['score']:.2f}")
                b.metric("Attempted", f"{result['attempted']}/{len(attempt['questions'])}")
                c.metric("Accuracy", f"{result['accuracy']:.1f}%")
                d.metric("Correct / Wrong", f"{result['correct_count']} / {result['wrong_count']}")
                st.subheader("Subject-wise summary")
                st.dataframe(
                    [{"Subject": k, "Correct": v["correct"], "Wrong": v["wrong"],
                      "Unattempted": v["unattempted"], "Net marks": round(v["marks"], 2)}
                     for k, v in result["per_subject"].items()],
                    use_container_width=True, hide_index=True
                )
                st.subheader("Review answers")
                for idx, q in enumerate(attempt["questions"], start=1):
                    with st.expander(f"Q{idx}. {q['question'][:90]}"):
                        st.markdown(q["question"])
                        st.write("Your answer:", attempt["answers"].get(q["id"], "Not attempted"))
                        st.write("Correct answer:", q.get("answer", "Not provided"))
                        if q.get("explanation"):
                            st.write("Explanation:", q["explanation"])
                if st.button("Clear attempt and return to setup"):
                    st.session_state.pop("attempt", None)
                    st.rerun()
            else:
                remaining = max(0, attempt["duration_seconds"] - int(time.time() - attempt["start_time"]))
                mins, secs = divmod(remaining, 60)
                st.markdown(f"### {attempt['paper_title']}")
                st.metric("Time remaining", f"{mins:02d}:{secs:02d}")
                st.progress(1 - remaining / attempt["duration_seconds"])
                questions = attempt["questions"]
                idx = min(attempt["index"], len(questions) - 1)
                q = questions[idx]
                st.markdown(f"**Question {idx + 1} of {len(questions)}** · {q['type']} · {q['marks']} mark(s)")
                st.markdown('<div class="question-card">', unsafe_allow_html=True)
                st.markdown(q["question"])
                st.markdown('</div>', unsafe_allow_html=True)

                qid = q["id"]
                existing = attempt["answers"].get(qid)
                if q["type"] == "NAT":
                    val = st.text_input("Enter numerical answer", value="" if existing is None else str(existing), key=f"nat_{qid}")
                    attempt["answers"][qid] = val.strip() if val.strip() else None
                elif q["type"] == "MSQ":
                    opts = q["options"]
                    selected = st.multiselect("Select all correct options", list(opts.keys()),
                                              default=existing if isinstance(existing, list) else [],
                                              format_func=lambda k: f"{k}. {opts[k]}", key=f"msq_{qid}")
                    attempt["answers"][qid] = selected or None
                else:
                    opts = q["options"]
                    keys = list(opts.keys())
                    selected = st.radio("Choose one answer", keys,
                                         index=keys.index(existing) if existing in keys else None,
                                         format_func=lambda k: f"{k}. {opts[k]}", key=f"mcq_{qid}")
                    attempt["answers"][qid] = selected

                mark = st.checkbox("Mark for review", value=qid in attempt["marked"], key=f"mark_{qid}")
                if mark:
                    attempt["marked"].add(qid)
                else:
                    attempt["marked"].discard(qid)

                st.divider()
                nav1, nav2, nav3, nav4 = st.columns(4)
                with nav1:
                    if st.button("← Previous", disabled=idx == 0, use_container_width=True):
                        attempt["index"] = idx - 1
                        st.rerun()
                with nav2:
                    if st.button("Next →", disabled=idx == len(questions) - 1, use_container_width=True):
                        attempt["index"] = idx + 1
                        st.rerun()
                with nav3:
                    st.caption(f"Answered: {sum(1 for v in attempt['answers'].values() if v not in (None, '', []))}")
                    st.caption(f"Marked: {len(attempt['marked'])}")
                with nav4:
                    if st.button("Submit test", type="primary", use_container_width=True):
                        attempt["submitted"] = True
                        st.rerun()
                st.markdown("**Jump to question**")
                cols = st.columns(8)
                for i, question in enumerate(questions):
                    q_answered = attempt["answers"].get(question["id"]) not in (None, "", [])
                    label = f"{i+1} ✓" if q_answered else str(i+1)
                    if question["id"] in attempt["marked"]:
                        label += " ⚑"
                    with cols[i % 8]:
                        if st.button(label, key=f"jump_{i}", use_container_width=True):
                            attempt["index"] = i
                            st.rerun()
                st.caption("Timer check occurs when the app reruns (for example, after an answer or navigation click). Do not rely on this starter version as a proctored or high-stakes exam platform.")

st.divider()
st.caption("Starter project • Your uploaded files are processed by this app session. Do not upload confidential documents to a public deployment.")
