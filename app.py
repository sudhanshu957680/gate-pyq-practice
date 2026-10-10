import re
import time
import fitz
import streamlit as st
from streamlit_autorefresh import st_autorefresh

st.set_page_config(page_title="GATE PYQ CBT", page_icon="📝", layout="wide")

# GATE-inspired CBT layout: clean exam header, question pane, palette and footer.
st.markdown("""
<style>
:root { --navy:#163b67; --blue:#1769aa; --green:#25834a; --red:#c53d3d; --purple:#7650a8; }
.block-container {max-width: 1500px; padding-top: .7rem; padding-bottom: 1rem;}
header[data-testid="stHeader"] {height: 2.2rem;}
.exam-top {background:#173b66;color:#fff;padding:12px 18px;border-radius:8px;margin-bottom:12px;}
.exam-top h2 {color:#fff;margin:0;font-size:1.25rem;}
.exam-sub {font-size:.9rem;opacity:.9;margin-top:4px;}
.panel {border:1px solid #c8d1dc;border-radius:8px;padding:14px;background:var(--secondary-background-color);}
.question-title {font-size:1.05rem;font-weight:700;margin-bottom:12px;}
.legend {display:flex;flex-wrap:wrap;gap:10px;font-size:.82rem;margin:8px 0 12px;}
.legend span {display:inline-flex;align-items:center;gap:5px;}
.dot {width:11px;height:11px;display:inline-block;border-radius:3px;}
div.stButton > button {border-radius:6px;min-height:2.5rem;}
div[data-testid="stRadio"] label {padding:8px 10px;border:1px solid #cfd6df;border-radius:7px;margin-bottom:7px;width:100%;}
div[data-testid="stRadio"] label:hover {border-color:#1769aa;}
.small-note {font-size:.82rem;color:gray;}
</style>
""", unsafe_allow_html=True)

def extract_pdf_text(uploaded):
    doc = fitz.open(stream=uploaded.getvalue(), filetype="pdf")
    text = "\n".join(page.get_text("text") for page in doc)
    doc.close()
    return text.strip()

def split_questions(text):
    # GATE master papers commonly use labels like "Q.1", "Q. 1", sometimes "1."
    text = text.replace("\r", "\n")
    pat = re.compile(r"(?m)^\s*(?:Q\s*\.\s*(\d{1,3})|Question\s*(\d{1,3})\s*[:.)]|(\d{1,3})[.)])\s*")
    matches = list(pat.finditer(text))
    blocks = []
    for i, m in enumerate(matches):
        n = next((x for x in m.groups() if x), None)
        end = matches[i+1].start() if i+1 < len(matches) else len(text)
        block = text[m.end():end].strip()
        if n and len(block) >= 8:
            blocks.append({"number":str(int(n)), "raw":block})
    unique = {}
    for q in blocks:
        # Keep first reasonable block per question number; page footer duplicates are discarded.
        if q["number"] not in unique:
            unique[q["number"]] = q
    return list(unique.values())

def get_options(raw):
    # Handles (A), (B), (C), (D), and A. / A) styles.
    pat = re.compile(r"(?im)^\s*\(?([A-D])\)?[.)]\s+")
    ms = list(pat.finditer(raw))
    options = {}
    if len(ms) >= 2:
        for i, m in enumerate(ms):
            end = ms[i+1].start() if i+1 < len(ms) else len(raw)
            val = re.sub(r"\s+", " ", raw[m.end():end]).strip()
            if val:
                options[m.group(1).upper()] = val
    if options:
        first = ms[0].start()
        stem = raw[:first].strip()
    else:
        stem = raw.strip()
    return stem, options

def parse_answer_key(text):
    answers = {}
    # Common one-line formats: Q.1 A, 1: A, 1 A, 1 = 2.5, 1 A,C
    patterns = [
        re.compile(r"(?im)^\s*Q\s*\.?\s*(\d{1,3})\s*[:.)=\-]\s*([A-D](?:\s*[,/]\s*[A-D])*)\s*$"),
        re.compile(r"(?im)^\s*(\d{1,3})\s*[:.)=\-]\s*([A-D](?:\s*[,/]\s*[A-D])*)\s*$"),
        re.compile(r"(?im)^\s*(\d{1,3})\s+([A-D](?:\s*[,/]\s*[A-D])*)\s*$"),
        re.compile(r"(?im)^\s*(?:Q\s*\.?\s*)?(\d{1,3})\s*[:.)=\-]\s*(-?\d+(?:\.\d+)?)\s*$"),
        re.compile(r"(?im)^\s*(\d{1,3})\s+(-?\d+(?:\.\d+)?)\s*$"),
    ]
    for pat in patterns:
        for m in pat.finditer(text):
            n, value = m.group(1), m.group(2).strip()
            if n in answers: continue
            if re.fullmatch(r"[A-D](?:\s*[,/]\s*[A-D])*", value, re.I):
                answers[n] = [x.upper() for x in re.split(r"\s*[,/]\s*", value)]
            else:
                try: answers[n] = float(value)
                except ValueError: pass

    # Table extraction fallback: GATE answer keys often extract one cell per line.
    # Detect question number followed nearby by key-like value, but only when a simple row pattern exists.
    lines = [re.sub(r"\s+", " ", x).strip() for x in text.splitlines() if x.strip()]
    for i, line in enumerate(lines):
        m = re.fullmatch(r"(?:Q\s*\.?\s*)?(\d{1,3})", line, re.I)
        if not m or m.group(1) in answers: continue
        n = m.group(1)
        nearby = lines[i+1:min(i+8, len(lines))]
        for candidate in nearby:
            if re.fullmatch(r"[A-D](?:\s*[,/]\s*[A-D])*", candidate, re.I):
                answers[n] = [x.upper() for x in re.split(r"\s*[,/]\s*", candidate)]
                break
            if re.fullmatch(r"-?\d+(?:\.\d+)?\s*(?:to|–|-)\s*-?\d+(?:\.\d+)?", candidate, re.I):
                nums = re.findall(r"-?\d+(?:\.\d+)?", candidate)
                answers[n] = (float(nums[0]) + float(nums[1])) / 2
                break
            if re.fullmatch(r"-?\d+(?:\.\d+)?", candidate):
                try:
                    answers[n] = float(candidate)
                    break
                except ValueError: pass
    return answers

def answer_text(a):
    if a is None: return ""
    if isinstance(a, list): return ",".join(a)
    return str(a)

def parse_answer_value(s, qtype):
    s = s.strip()
    if not s: return None
    if qtype == "NAT":
        try: return float(s)
        except ValueError: return None
    vals = [x.strip().upper() for x in re.split(r"[,/]", s) if x.strip()]
    return vals if qtype == "MSQ" else (vals[0] if vals else None)

def is_blank(x):
    return x is None or x == "" or x == []

def score_test(questions, responses):
    score = 0.0; correct = wrong = attempted = 0
    for q in questions:
        ans = responses.get(q["id"])
        if is_blank(ans): continue
        attempted += 1
        expected = q["answer"]
        ok = False
        if q["type"] == "NAT":
            try: ok = abs(float(ans) - float(expected)) <= q.get("tolerance", 0.0)
            except (ValueError, TypeError): ok = False
        elif q["type"] == "MSQ":
            ok = set(ans if isinstance(ans, list) else [ans]) == set(expected if isinstance(expected, list) else [expected])
        else:
            ok = str(ans).upper() == str(expected).upper()
        if ok:
            score += q["marks"]; correct += 1
        else:
            score -= q["negative"]; wrong += 1
    return score, correct, wrong, attempted, len(questions)-attempted

def build_questions(qtext, atext, marks_1, marks_2, neg):
    blocks = split_questions(qtext)
    key = parse_answer_key(atext)
    out = []
    for b in blocks:
        stem, opts = get_options(b["raw"])
        ans = key.get(b["number"])
        qtype = "MSQ" if isinstance(ans, list) and len(ans)>1 else ("MCQ" if opts else "NAT")
        out.append({
            "id": b["number"], "number": b["number"], "question": stem or b["raw"],
            "options": opts, "type": qtype, "answer": ans,
            "marks": float(marks_2 if int(b["number"]) > 10 else marks_1),
            "negative": float(neg if qtype == "MCQ" else 0),
            "tolerance": 0.0, "raw": b["raw"]
        })
    return out, key

# Session state defaults
if "prepared_questions" not in st.session_state: st.session_state.prepared_questions = []
if "responses" not in st.session_state: st.session_state.responses = {}
if "review" not in st.session_state: st.session_state.review = set()
if "current" not in st.session_state: st.session_state.current = 0
if "started_at" not in st.session_state: st.session_state.started_at = None
if "duration_sec" not in st.session_state: st.session_state.duration_sec = 180*60
if "submitted" not in st.session_state: st.session_state.submitted = False

st.markdown('<div class="exam-top"><h2>GATE PYQ PRACTICE</h2><div class="exam-sub">Computer-Based Test Practice • Question paper + official answer key</div></div>', unsafe_allow_html=True)

with st.sidebar:
    st.header("Test setup")
    year = st.selectbox("GATE year", [str(y) for y in range(2026, 2009, -1)] + ["Older / other"])
    paper = st.selectbox("Paper", ["Computer Science (CS)", "Data Science & AI (DA)", "Electronics (EC)", "Electrical (EE)", "Other"])
    session_name = st.text_input("Session / shift", placeholder="e.g. CS1")
    duration = st.number_input("Duration (minutes)", min_value=1, max_value=240, value=180, step=5)
    mark_1 = st.number_input("1-mark question marks", min_value=0.0, max_value=5.0, value=1.0, step=0.5)
    mark_2 = st.number_input("2-mark question marks", min_value=0.0, max_value=5.0, value=2.0, step=0.5)
    neg = st.selectbox("MCQ negative marking", [0.0, 0.25, 0.33, 0.5, 0.66], index=2)
    st.caption("Confirm each paper's official marking scheme before scoring.")

# Setup/upload view until user prepares a test
if not st.session_state.prepared_questions:
    st.subheader("Prepare your paper")
    c1, c2 = st.columns(2)
    with c1:
        qpdf = st.file_uploader("1. Upload question paper PDF", type=["pdf"], key="qpdf")
    with c2:
        apdf = st.file_uploader("2. Upload official answer key PDF", type=["pdf"], key="apdf")
    if qpdf and apdf:
        try:
            qtext = extract_pdf_text(qpdf)
            atext = extract_pdf_text(apdf)
            with st.expander("Preview extracted question text"):
                st.text_area("Question paper text", qtext, height=180, key="qtext_preview")
            with st.expander("Preview / correct answer-key text", expanded=True):
                atext = st.text_area("Answer-key text", atext, height=180, key="atext_edit")
            questions, key = build_questions(qtext, atext, mark_1, mark_2, neg)
            st.info(f"Detected {len(questions)} question blocks and {len(key)} answer-key entries. Review the extracted text before starting.")
            if questions:
                with st.expander("Review detected questions", expanded=False):
                    for q in questions:
                        st.markdown(f"**Q{q['number']}** — {q['question'][:220]}")
                        st.caption(f"Options detected: {len(q['options'])} • Key answer: {answer_text(q['answer']) or 'NOT DETECTED'}")
            if st.button("Prepare CBT test", type="primary", use_container_width=True):
                st.session_state.prepared_questions = questions
                st.session_state.paper_title = f"GATE {paper} {year}" + (f" — {session_name}" if session_name else "")
                st.session_state.duration_sec = int(duration*60)
                st.session_state.responses = {}
                st.session_state.review = set()
                st.session_state.current = 0
                st.session_state.started_at = None
                st.session_state.submitted = False
                st.rerun()
        except Exception as e:
            st.error(f"Could not process one of the PDFs: {e}")
    else:
        st.caption("Upload both PDFs to extract text. Scanned/image-only PDFs need OCR and are not supported in this no-API version.")
    st.stop()

# Exam view
questions = st.session_state.prepared_questions
if not questions:
    st.error("No questions were extracted. Clear the test and upload text-based PDFs with selectable text.")
    if st.button("Back to setup"): st.session_state.prepared_questions=[]; st.rerun()
    st.stop()

if st.session_state.started_at is None and not st.session_state.submitted:
    st.subheader(st.session_state.get("paper_title", "GATE Practice Test"))
    st.write(f"**{len(questions)} questions** • **{st.session_state.duration_sec//60} minutes**")
    st.warning("Before starting, verify question extraction and answer-key mapping. Do not use scores until all answers are checked.")
    if st.button("Start examination", type="primary"):
        st.session_state.started_at = time.time()
        st.rerun()
    if st.button("Return to upload / reset"):
        st.session_state.prepared_questions=[]
        st.rerun()
    st.stop()

if st.session_state.submitted:
    score, correct, wrong, attempted, unattempted = score_test(questions, st.session_state.responses)
    st.success("Test submitted.")
    m1,m2,m3,m4 = st.columns(4)
    m1.metric("Score (estimated)", f"{score:.2f}")
    m2.metric("Correct", correct)
    m3.metric("Wrong", wrong)
    m4.metric("Unattempted", unattempted)
    st.caption("Estimated score uses the marks and answer key imported into this app. Verify the official marking scheme and key.")
    for q in questions:
        with st.expander(f"Q{q['number']} — review"):
            st.write(q["question"])
            st.write("Your answer:", st.session_state.responses.get(q["id"], "Not answered"))
            st.write("Key answer:", answer_text(q["answer"]) or "Not detected")
            for letter, opt in q["options"].items(): st.write(f"{letter}. {opt}")
    if st.button("Start another paper"):
        for k in ["prepared_questions","responses","review","current","started_at","submitted"]:
            st.session_state.pop(k, None)
        st.rerun()
    st.stop()

st_autorefresh(interval=1000, key="exam_timer_refresh")
remaining = max(0, st.session_state.duration_sec - int(time.time()-st.session_state.started_at))
if remaining <= 0:
    st.session_state.submitted = True
    st.rerun()

# Header status
mins, secs = divmod(remaining, 60)
top1, top2, top3 = st.columns([5,2,2])
with top1:
    st.markdown(f"### {st.session_state.get('paper_title','GATE Practice Test')}")
    st.caption("Choose the most appropriate answer. Use Mark for Review when needed.")
with top2:
    st.metric("Time left", f"{mins:02d}:{secs:02d}")
with top3:
    st.metric("Question", f"{st.session_state.current+1} / {len(questions)}")

st.progress(remaining / st.session_state.duration_sec)
st.divider()

# Two-column CBT layout
left, right = st.columns([3.5, 1.15], gap="large")
idx = min(st.session_state.current, len(questions)-1)
q = questions[idx]
with left:
    st.markdown(f'<div class="panel"><div class="question-title">Question {idx+1} <span style="font-weight:400;color:#667085">| {q["type"]} | {q["marks"]:g} mark(s)</span></div></div>', unsafe_allow_html=True)
    st.markdown(q["question"] if q["question"].strip() else "_Question text was not extracted. Return to setup and inspect the PDF text._")
    if not q["question"].strip():
        st.warning("This question has no extracted text. The PDF may use a layout that needs manual correction.")
    qid = q["id"]
    opts = q["options"]
    if q["type"] == "NAT" or not opts:
        prior = st.session_state.responses.get(qid, "")
        response = st.text_input("Enter numerical answer", value=str(prior) if prior is not None else "", key=f"nat_{qid}")
        st.session_state.responses[qid] = response.strip() if response.strip() else None
    elif q["type"] == "MSQ":
        prior = st.session_state.responses.get(qid, [])
        response = st.multiselect("Select all correct options", list(opts.keys()), default=prior if isinstance(prior,list) else [], format_func=lambda k: f"{k}. {opts[k]}", key=f"msq_{qid}")
        st.session_state.responses[qid] = response or None
    else:
        keys = list(opts.keys())
        prior = st.session_state.responses.get(qid)
        response = st.radio("Select one answer", keys, index=keys.index(prior) if prior in keys else None, format_func=lambda k: f"{k}. {opts[k]}", key=f"mcq_{qid}")
        st.session_state.responses[qid] = response
    st.divider()
    b1,b2,b3,b4 = st.columns([1.2,1.5,1.5,1.5])
    with b1:
        if st.button("← Previous", disabled=idx==0, use_container_width=True):
            st.session_state.current -= 1; st.rerun()
    with b2:
        if st.button("Clear response", use_container_width=True):
            st.session_state.responses[qid] = None; st.rerun()
    with b3:
        if st.button("Mark for review", use_container_width=True):
            st.session_state.review.add(qid); st.session_state.current = min(idx+1,len(questions)-1); st.rerun()
    with b4:
        if st.button("Save & Next", type="primary", use_container_width=True):
            st.session_state.current = min(idx+1,len(questions)-1); st.rerun()

with right:
    st.markdown('<div class="panel"><div class="question-title">Question Palette</div></div>', unsafe_allow_html=True)
    st.markdown("""
    <div class="legend">
    <span><i class="dot" style="background:#25834a"></i>Answered</span>
    <span><i class="dot" style="background:#7650a8"></i>Review</span>
    <span><i class="dot" style="background:#d5dbe3"></i>Not answered</span>
    </div>
    """, unsafe_allow_html=True)
    cols = st.columns(5)
    for i, item in enumerate(questions):
        qid2 = item["id"]
        ans = st.session_state.responses.get(qid2)
        if qid2 in st.session_state.review: label = f"⚑ {i+1}"
        elif not is_blank(ans): label = f"✓ {i+1}"
        else: label = str(i+1)
        with cols[i % 5]:
            if st.button(label, key=f"jump_{i}", use_container_width=True):
                st.session_state.current = i; st.rerun()
    st.divider()
    st.caption(f"Answered: {sum(not is_blank(st.session_state.responses.get(x['id'])) for x in questions)} / {len(questions)}")
    if st.button("Submit examination", type="primary", use_container_width=True):
        st.session_state.submitted = True; st.rerun()


