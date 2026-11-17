# 🎤 AI Interview Assistant

A voice-enabled mock interview app for **any job role**. Choose a role and a difficulty
level, and the AI interviewer asks role-specific questions out loud. You answer by
speaking or typing, get feedback after every answer, and receive a final score at the end.

## Features
- Choose any job role (Data Analyst, Web Developer, Accountant, ...) and a difficulty level
- AI plans interview topics for the chosen role and asks one question at a time
- Voice input: speak your answer (speech-to-text with Gemini)
- Voice output: the interviewer speaks in a natural voice (edge-tts, with gTTS as backup)
- Instant feedback after each answer, plus a final score out of 10 with strengths and improvements
- Automatic retry and backup model when the API is busy

## Tech Stack
Python, Streamlit, Google Gemini API, edge-tts, gTTS

## How to Run
1. Clone the repo

        git clone https://github.com/Shobhish/ai-interview-assistant.git
        cd ai-interview-assistant

2. Create a virtual environment and install packages

        python -m venv venv
        venv\Scripts\activate
        pip install -r requirements.txt

3. Create a `.env` file and add your Gemini API key

        GEMINI_API_KEY=your_key_here

4. Run the app

        streamlit run app.py

## Customize
Edit the `LEVELS` dictionary in `app.py` to change how hard the questions are.

## Future Improvements
- Upload a resume for personalized questions
- Save interview history and scores
- Deploy online for easy use on mobile