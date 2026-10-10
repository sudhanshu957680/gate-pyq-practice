import re
import time
from pathlib import Path

import fitz  # PyMuPDF
import streamlit as st

st.set_page_config(page_title="GATE PYQ Practice", page_icon="📝", layout="wide")

st.markdown("""
<style>
.block-container {max-width: 1250px; padding-top: 1.4rem;}
.question-card {padding: 1rem; border: 1px solid rgba(128,128,128,.35); border-radius: 12px; margin: .5rem 0;}
</style>
""", unsafe_allow_html=True)

st.title("📝 GATE PYQ Practice")
st.caption("Upload a question paper PDF, then its official answer key PDF. Review the extracted content before starting a test.")

def extract_pdf_text(uploaded_file):
    """Extract selectable text from a PDF in memory. No API key or external service required."""
    data = uploaded_file.getvalue()
    doc = fitz.open(stream=data, filetype="pdf")
    pages = []
    for page_no, page in enumerate(doc, start=1):
        pages.append(f"\n\n--- PAGE {page_no} ---\n" + page.get_text("text"))
    doc.close()
    return "\n".join(pages).strip()

def split_question_blocks(text):
    """
    Heuristic parser for text-based papers.
    Looks for question numbers at the start of a line, such as '1.', '1)' or 'Q. 1'.
    PDF layouts vary, so users must review the result.
    """
    normalized = text.replace("\r", "\n")
    pattern = re.compile(r"(?m)^\s*(?:Q(?:uestion)?\s*\.?\s*(\d{1,3})|(\d{1,3})\s*[.)])\s+")
    matches = list(pattern.finditer(normalized))
    blocks = []
    for i, match in enumerate(matches):
        start = match.start()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(normalized)
        body = normalized[start:end].strip()
        # Skip section headings such as "Q.1 – Q.5 Carry ONE mark Each".
        if re.match(r"^Q(?:uestion)?\s*\.?\s*\d+\s*[–—-]\s*Q?\s*\d+", body, flags=re.I):
            continue
        # Exclude obvious page markers and empty chunks
        if len(body) >= 8:
            blocks.append((match.group(1) or match.group(2), body))
    # Keep first occurrence of each question number
    unique, seen = [], set()
    for number, body in blocks:
        if number not in seen:
            unique.append((number, body))
            seen.add(number)
    return unique

def parse_options(block):
    # Common option patterns: (A), A), A., (a)
    pattern = re.compile(r"(?im)(?:^|\n)\s*\(?([A-D])\)?[.)]\s+")
    matches = list(pattern.finditer(block))
    options = {}
    if len(matches) >= 2:
        for i, m in enumerate(matches):
            end = matches[i + 1].start() if i + 1 < len(matches) else len(block)
            value = block[m.end():end].strip()
            value = re.sub(r"\s+", " ", value)
            if value:
                options[m.group(1).upper()] = value
    return options

def strip_question_number(block):
    return re.sub(r"^\s*(?:Q(?:uestion)?\.?\s*)?\d{1,3}\s*[.)]\s*", "", block, count=1, flags=re.I).strip()

def parse_answer_key(text):
    """
    Best-effort answer-key parser. Supports common text formats such as:
    1 A
    Q1: B
    2. C
    4 = 3.14
    For MSQ keys, formats such as '5: A,C' may be recognized.
    """
    answers = {}
    patterns = [
        re.compile(r"(?im)^\s*(?:Q(?:uestion)?\.?\s*)?(\d{1,3})\s*[:.)=\-]\s*([A-D](?:\s*[,/]\s*[A-D])*)\s*$"),
        re.compile(r"(?im)^\s*(?:Q(?:uestion)?\.?\s*)?(\d{1,3})\s+([A-D](?:\s*[,/]\s*[A-D])*)\s*$"),
        re.compile(r"(?im)^\s*(?:Q(?:uestion)?\.?\s*)?(\d{1,3})\s*[:.)=\-]\s*(-?\d+(?:\.\d+)?)\s*$"),
        re.compile(r"(?im)^\s*(?:Q(?:uestion)?\.?\s*)?(\d{1,3})\s+(-?\d+(?:\.\d+)?)\s*$"),
    ]
    for pattern in patterns:
        for m in pattern.finditer(text):
            number, answer = m.group(1), m.group(2).strip()
            if number not in answers:
                if re.fullmatch(r"[A-D](?:\s*[,/]\s*[A-D])*", answer, flags=re.I):
                    answers[number] = [x.upper() for x in re.split(r"\s*[,/]\s*", answer)]
                else:
                    try:
                        answers[number] = float(answer)
                    except ValueError:
                        pass
    return answers

def infer_type(block, answer):
    if isinstance(answer, list) and len(answer) > 1:
        return "MSQ"
    if not parse_options(block):
        return "NAT"
    return "MCQ"

def make_questions(blocks, answers, default_marks, default_negative):
    questions = []
    for number, block in blocks:
        answer = answers.get(number)
        options = parse_options(block)
        qtype = infer_type(block, answer)
        question_text = strip_question_number(block)
        # If options were recognized, remove their text from the question stem.
        if options:
            option_match = re.search(r"(?im)(?:^|\n)\s*\(?A\)?[.)]\s+", question_text)
            if option_match:
                question_text = question_text[:option_match.start()].strip()
        if not question_text:
            question_text = block
        questions.append({
            "id": str(number),
            "number": str(number),
            "question": question_text,
            "type": qtype,
            "options": options,
            "answer": answer,
            "marks": float(default_marks),
            "negative_marks": float(default_negative if qtype == "MCQ" else 0),
            "subject": "Uncategorized",
            "explanation": "",
            "raw_block": block,
        })
    return questions

def answer_is_empty(value):
    return value is None or value == "" or value == []

def grade_attempt(questions, answers):
    score, attempted, correct, wrong, unattempted = 0.0, 0, 0, 0, 0
    subject_stats = {}
    for q in questions:
        user_answer = answers.get(q["id"])
        expected = q.get("answer")
        subject = q.get("subject") or "Uncategorized"
        stats = subject_stats.setdefault(subject, {"correct": 0, "wrong": 0, "unattempted": 0, "marks": 0.0})
        if answer_is_empty(user_answer):
            unattempted += 1
            stats["unattempted"] += 1
            continue
        attempted += 1
        is_correct = False
        if q["type"] == "NAT":
            try:
                is_correct = abs(float(user_answer) - float(expected)) <= float(q.get("tolerance", 0))
            except (TypeError, ValueError):
                is_correct = False
        elif q["type"] == "MSQ":
            expected_list = expected if isinstance(expected, list) else [expected]
            is_correct = set(user_answer) == set(expected_list)
        else:
            is_correct = str(user_answer).upper() == str(expected).upper()
        if is_correct:
            score += float(q["marks"])
            correct += 1
            stats["correct"] += 1
            stats["marks"] += float(q["marks"])
        else:
            penalty = float(q.get("negative_marks", 0)) if q["type"] == "MCQ" else 0.0
            score -= penalty
            wrong += 1
            stats["wrong"] += 1
            stats["marks"] -= penalty
    return {
        "score": score, "attempted": attempted, "correct": correct, "wrong": wrong,
        "unattempted": unattempted, "accuracy": correct / attempted * 100 if attempted else 0,
        "subjects": subject_stats
    }

# Sidebar paper metadata
with st.sidebar:
    st.header("Paper setup")
    year = st.selectbox("GATE year", [str(y) for y in range(2026, 2009, -1)] + ["Older / other"])
    paper_name = st.selectbox("Paper", ["GATE CSE", "GATE DA", "GATE ECE", "GATE EE", "Other"])
    session_name = st.text_input("Session / shift (optional)", placeholder="e.g. CSE Session 1")
    duration_minutes = st.number_input("Test duration (minutes)", min_value=1, max_value=240, value=180, step=5)
    default_marks = st.selectbox("Default marks per question", [1.0, 2.0], index=0)
    default_negative = st.selectbox("Default incorrect-MCQ penalty", [0.0, 0.25, 0.33, 0.5, 0.66], index=2)
    st.caption("Check the official marking scheme. You can correct marks and answers before the test.")

st.header("1. Upload the question paper")
question_pdf = st.file_uploader("Question paper PDF", type=["pdf"], key="question_pdf")
if question_pdf:
    try:
        extracted_questions = extract_pdf_text(question_pdf)
        st.session_state["question_pdf_text"] = extracted_questions
        st.session_state["question_pdf_name"] = question_pdf.name
        st.success(f"Extracted selectable text from {question_pdf.name}")
        with st.expander("Preview extracted question-paper text"):
            st.text_area("Extracted text (read-only preview)", extracted_questions, height=220, disabled=True)
        if not extracted_questions.strip():
            st.warning("No selectable text was found. This may be a scanned PDF. This no-API version cannot OCR scanned pages; you will need a text-based PDF or manual entry.")
    except Exception as exc:
        st.error(f"Could not read this PDF: {exc}")

st.header("2. Upload the official answer key")
answer_pdf = st.file_uploader("Official answer key PDF", type=["pdf"], key="answer_pdf")
if answer_pdf:
    try:
        extracted_key = extract_pdf_text(answer_pdf)
        st.session_state["answer_pdf_text"] = extracted_key
        st.session_state["answer_pdf_name"] = answer_pdf.name
        st.success(f"Extracted selectable text from {answer_pdf.name}")
        with st.expander("Preview extracted answer-key text"):
            st.text_area("Extracted answer-key text (editable)", extracted_key, height=220, key="answer_text_edit")
    except Exception as exc:
        st.error(f"Could not read this answer-key PDF: {exc}")

question_text = st.session_state.get("question_pdf_text", "")
key_text_default = st.session_state.get("answer_pdf_text", "")

if question_text and key_text_default:
    st.header("3. Extract and review")
    st.info("Automatic extraction uses text-layout heuristics. Question numbering and answer-key layouts vary between PDFs. Always verify the extracted questions and answers before starting a scored test.")
    with st.expander("Edit extracted question text if the PDF parser missed or joined lines", expanded=False):
        question_text = st.text_area("Question-paper text (editable)", question_text, height=300, key="question_text_edit")
    key_text = st.session_state.get("answer_text_edit", key_text_default)
    key_text = st.text_area("Answer-key text (editable; fix entries if needed)", key_text, height=180, key="answer_text_final")
    blocks = split_question_blocks(question_text)
    parsed_answers = parse_answer_key(key_text)
    questions = make_questions(blocks, parsed_answers, default_marks, default_negative)

    st.write(f"**Detected question blocks:** {len(blocks)} · **Detected answer-key entries:** {len(parsed_answers)}")
    if not blocks:
        st.warning("No question blocks were detected. The PDF may have unusual formatting. Edit the extracted question text above or use manual entry below.")
    if not parsed_answers:
        st.warning("No answer-key entries were detected. Edit the answer-key text to a recognizable format, such as `1 A`, `2 C`, `3 2.5`, then try again.")

    if questions:
        # A compact manual review editor: question stem, type, answer, marks, penalty, subject, options as readable JSON-like text.
        st.markdown("### Review questions and answer mapping")
        st.caption("Edit question text, answer, type, marks, penalty, and subject below. For MCQ/MSQ answers, use option letters (e.g. B or A,C). For NAT, enter a number.")
        edited = []
        for i, q in enumerate(questions):
            with st.expander(f"Q{q['number']} — {q['question'][:100]}", expanded=(i < 2)):
                q["question"] = st.text_area("Question text", q["question"], key=f"stem_{q['id']}", height=120)
                if q["options"]:
                    st.markdown("**Detected options**")
                    for letter, option_text in q["options"].items():
                        st.write(f"{letter}. {option_text}")
                    option_fix = st.text_area(
                        "Options (one per line: A: option text)",
                        "\n".join(f"{k}: {v}" for k, v in q["options"].items()),
                        key=f"opts_{q['id']}", height=100
                    )
                    fixed_options = {}
                    for line in option_fix.splitlines():
                        if ":" in line:
                            letter, value = line.split(":", 1)
                            letter = letter.strip().upper()
                            if letter in ["A", "B", "C", "D"] and value.strip():
                                fixed_options[letter] = value.strip()
                    q["options"] = fixed_options
                q["type"] = st.selectbox("Question type", ["MCQ", "MSQ", "NAT"],
                                         index=["MCQ", "MSQ", "NAT"].index(q["type"]),
                                         key=f"type_{q['id']}")
                answer_default = ",".join(q["answer"]) if isinstance(q["answer"], list) else ("" if q["answer"] is None else str(q["answer"]))
                answer_text = st.text_input("Correct answer from key (edit if needed)", answer_default, key=f"answer_{q['id']}")
                if q["type"] == "MSQ":
                    q["answer"] = [x.strip().upper() for x in re.split(r"[,/]", answer_text) if x.strip()]
                elif q["type"] == "MCQ":
                    q["answer"] = answer_text.strip().upper() or None
                else:
                    try:
                        q["answer"] = float(answer_text) if answer_text.strip() else None
                    except ValueError:
                        q["answer"] = None
                c1, c2, c3 = st.columns(3)
                with c1:
                    q["marks"] = st.number_input("Marks", min_value=0.0, max_value=10.0, value=float(q["marks"]), step=0.5, key=f"marks_{q['id']}")
                with c2:
                    q["negative_marks"] = st.number_input("Negative marks (MCQ only)", min_value=0.0, max_value=5.0, value=float(q["negative_marks"]), step=0.01, key=f"neg_{q['id']}")
                with c3:
                    q["subject"] = st.text_input("Subject", q["subject"], key=f"subject_{q['id']}")
                q["explanation"] = st.text_area("Explanation (optional)", q["explanation"], key=f"explain_{q['id']}", height=70)
                edited.append(q)

        if st.button("Prepare reviewed test", type="primary"):
            # Validate the answer map before starting.
            missing = [q["number"] for q in questions if q["answer"] is None or q["answer"] == []]
            if missing:
                st.warning("Some questions have no detected answer: " + ", ".join(missing[:30]) + (f" (and {len(missing)-30} more)" if len(missing) > 30 else "") + ". Fill these answers or proceed only after correcting the key.")
            else:
                title = f"{paper_name} {year}" + (f" — {session_name}" if session_name.strip() else "")
                st.session_state["prepared_test"] = {
                    "title": title, "questions": questions, "duration": int(duration_minutes),
                    "question_file": st.session_state.get("question_pdf_name", ""),
                    "answer_file": st.session_state.get("answer_pdf_name", "")
                }
                st.success("Reviewed test prepared. Scroll to the test section below.")
                st.rerun()

st.header("4. Take the timed test")
prepared = st.session_state.get("prepared_test")
if not prepared:
    st.info("Upload both PDFs, review the extraction, and click **Prepare reviewed test** to enable the test.")
else:
    st.write(f"**{prepared['title']}** · {len(prepared['questions'])} questions · {prepared['duration']} minutes")
    if st.button("Start / restart test", type="primary"):
        st.session_state["attempt"] = {
            "answers": {}, "index": 0, "marked": set(), "start": time.time(),
            "duration": prepared["duration"] * 60, "submitted": False,
            "questions": prepared["questions"], "title": prepared["title"]
        }
        st.rerun()

    attempt = st.session_state.get("attempt")
    if attempt:
        remaining = max(0, attempt["duration"] - int(time.time() - attempt["start"]))
        if remaining == 0 and not attempt["submitted"]:
            attempt["submitted"] = True
            attempt["auto_submitted"] = True

        if attempt["submitted"]:
            result = grade_attempt(attempt["questions"], attempt["answers"])
            st.success("Time expired; test auto-submitted." if attempt.get("auto_submitted") else "Test submitted.")
            a, b, c, d = st.columns(4)
            a.metric("Score", f"{result['score']:.2f}")
            b.metric("Attempted", f"{result['attempted']}/{len(attempt['questions'])}")
            c.metric("Accuracy", f"{result['accuracy']:.1f}%")
            d.metric("Correct / wrong", f"{result['correct']} / {result['wrong']}")
            st.subheader("Subject-wise summary")
            st.dataframe([{"Subject": k, **v} for k, v in result["subjects"].items()], use_container_width=True, hide_index=True)
            st.subheader("Review answers")
            for i, q in enumerate(attempt["questions"], start=1):
                with st.expander(f"Q{q['number']} — {q['question'][:100]}"):
                    st.write("Your answer:", attempt["answers"].get(q["id"], "Not attempted"))
                    st.write("Correct answer:", q.get("answer", "Not available"))
                    if q.get("explanation"):
                        st.write("Explanation:", q["explanation"])
                    if q.get("options"):
                        for letter, value in q["options"].items():
                            st.write(f"{letter}. {value}")
            if st.button("Clear attempt"):
                st.session_state.pop("attempt", None)
                st.rerun()
        else:
            mins, secs = divmod(remaining, 60)
            st.metric("Time remaining", f"{mins:02d}:{secs:02d}")
            st.progress(max(0.0, min(1.0, remaining / attempt["duration"])))
            qs = attempt["questions"]
            idx = min(attempt["index"], len(qs) - 1)
            q = qs[idx]
            st.markdown(f"### Question {idx + 1} of {len(qs)} · {q['type']} · {q['marks']} mark(s)")
            st.markdown('<div class="question-card">', unsafe_allow_html=True)
            st.markdown(q["question"])
            st.markdown('</div>', unsafe_allow_html=True)
            qid = q["id"]
            existing = attempt["answers"].get(qid)
            if q["type"] == "NAT":
                val = st.text_input("Numerical answer", value="" if existing is None else str(existing), key=f"test_nat_{qid}")
                attempt["answers"][qid] = val.strip() if val.strip() else None
            elif q["type"] == "MSQ":
                options = q["options"]
                selected = st.multiselect("Select all correct options", list(options.keys()),
                    default=existing if isinstance(existing, list) else [],
                    format_func=lambda k: f"{k}. {options[k]}", key=f"test_msq_{qid}")
                attempt["answers"][qid] = selected or None
            else:
                options = q["options"]
                keys = list(options.keys())
                selected = st.radio("Choose one answer", keys,
                    index=keys.index(existing) if existing in keys else None,
                    format_func=lambda k: f"{k}. {options[k]}", key=f"test_mcq_{qid}")
                attempt["answers"][qid] = selected
            marked = st.checkbox("Mark for review", value=qid in attempt["marked"], key=f"test_mark_{qid}")
            if marked:
                attempt["marked"].add(qid)
            else:
                attempt["marked"].discard(qid)
            c1, c2, c3 = st.columns(3)
            with c1:
                if st.button("← Previous", disabled=idx == 0, use_container_width=True):
                    attempt["index"] = idx - 1
                    st.rerun()
            with c2:
                if st.button("Next →", disabled=idx >= len(qs)-1, use_container_width=True):
                    attempt["index"] = idx + 1
                    st.rerun()
            with c3:
                if st.button("Submit test", type="primary", use_container_width=True):
                    attempt["submitted"] = True
                    st.rerun()
            st.markdown("**Question palette**")
            palette_cols = st.columns(8)
            for i, item in enumerate(qs):
                answered = not answer_is_empty(attempt["answers"].get(item["id"]))
                label = f"{i+1}{' ✓' if answered else ''}{' ⚑' if item['id'] in attempt['marked'] else ''}"
                with palette_cols[i % 8]:
                    if st.button(label, key=f"palette_{i}", use_container_width=True):
                        attempt["index"] = i
                        st.rerun()

st.divider()
st.caption("PDF extraction runs locally within the hosted app process using PyMuPDF; no external AI API is used. Scanned PDFs need OCR, which is not included. Always verify extracted text, question numbering, options, answer mapping, and marking scheme.")
