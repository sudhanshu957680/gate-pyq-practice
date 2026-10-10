# GATE PYQ Practice — beginner starter project

A small Streamlit web app for practising GATE previous-year papers on a laptop or phone browser.

## What works in this first version

- Upload and view an original question-paper PDF.
- Set a practice duration and start a timer.
- Run an interactive test from a JSON question bank.
- Supports MCQ, MSQ, and NAT-style answers.
- Navigate questions, mark questions for review, and submit.
- Basic score, accuracy, and subject-wise results.
- Includes three **illustrative sample questions** so you can test the app immediately.

## Important limitations

1. The PDF viewer mode does **not** automatically read or grade the PDF. It displays the paper and gives you a separate practice timer.
2. Interactive mode uses structured JSON. You need to convert/enter questions, options, answer keys, marks, and explanations into JSON. PDF extraction can be added later, but equations, diagrams, and scanned pages need checking.
3. The timer in this beginner version checks expiry when Streamlit reruns (for example, after clicking a control). It is not a proctored or high-stakes exam system.
4. Sample questions are illustrative and are not represented as official GATE questions.
5. Confirm the marking scheme for each paper before using a question bank for scoring. The starter scoring logic applies negative marks to incorrect MCQs and no negative marks to MSQs/NATs; edit per-question settings if needed.

## Requirements

- Python 3.10 or newer
- Internet access for the first package installation

## Install on Windows

1. Extract the ZIP to a folder, for example `C:\gate_pyq_app`.
2. Install Python from https://www.python.org/downloads/ if it is not installed. During setup, select **Add Python to PATH**.
3. Open Command Prompt in the extracted folder.
4. Create a virtual environment:

   ```bat
   py -m venv .venv
   .venv\Scripts\activate
   ```

5. Install packages:

   ```bat
   python -m pip install --upgrade pip
   pip install -r requirements.txt
   ```

6. Start the app:

   ```bat
   streamlit run app.py
   ```

7. Streamlit will print a local URL, usually `http://localhost:8501`. Open it in your browser.

## Install on macOS / Linux

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
pip install -r requirements.txt
streamlit run app.py
```

## Open on your phone on the same Wi-Fi

You can run this locally on your laptop and then access it from a phone connected to the same Wi-Fi:

```bash
streamlit run app.py --server.address 0.0.0.0
```

Find your laptop's local IP address, then open `http://LAPTOP-IP:8501` on your phone. For example, replace `LAPTOP-IP` with your laptop's actual local IP address. This may require allowing Python through your laptop firewall. Do not expose this server to the public internet.

## JSON question-bank format

See `data/sample_questions.json`. Example:

```json
{
  "title": "GATE CSE 2024 practice",
  "questions": [
    {
      "id": "q1",
      "type": "MCQ",
      "subject": "Algorithms",
      "question": "Question text goes here",
      "options": {
        "A": "Option one",
        "B": "Option two",
        "C": "Option three",
        "D": "Option four"
      },
      "answer": "B",
      "marks": 1,
      "negative_marks": 0.33,
      "explanation": "Explanation goes here"
    }
  ]
}
```

### Fields

- `type`: `MCQ`, `MSQ`, or `NAT`
- `answer`: option letter for MCQ, array of option letters for MSQ, number for NAT
- `marks`: marks awarded for a correct answer
- `negative_marks`: penalty for an incorrect MCQ; use `0` for no penalty
- `subject`: used for the subject-wise report
- `explanation`: shown after submission
- Optional `tolerance` for NAT answers, e.g. `0.01`

## Suggested next steps

1. Test the app with the included sample bank.
2. Upload one real GATE PDF in PDF mode and check the display.
3. Add a JSON bank for one paper and compare the result against its official answer key.
4. Then add PDF-to-question extraction, diagrams, persistent attempt history, and improved timer handling.
