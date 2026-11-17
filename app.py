import asyncio
import io
import json
import os
import re
import time
import streamlit as st
import edge_tts
from dotenv import load_dotenv
from google import genai
from google.genai import types
from gtts import gTTS

load_dotenv()
client = genai.Client(
    api_key=os.getenv("GEMINI_API_KEY"),
    http_options=types.HttpOptions(timeout=30000),
)
MODELS = ["gemini-3.1-flash-lite", "gemini-3.5-flash"]  # main model, then backup

SUMMARY_MARKER = "---SUMMARY---"
VOICE = "en-IN-NeerjaNeural"   # try en-IN-PrabhatNeural (male) or en-US-GuyNeural
FALLBACK_TOPICS = [
    "Core skills for the role",
    "Tools and technologies",
    "Problem solving",
    "Past projects and experience",
]
LEVELS = {
    "Beginner / Fresher": "Ask simple, basic questions suitable for a fresher. Be encouraging. Avoid trick questions, deep edge cases, and advanced system design.",
    "Intermediate": "Ask practical questions suitable for someone with 1-3 years of experience.",
    "Advanced": "Ask challenging, in-depth questions suitable for a senior candidate.",
}


# ---------- Helper functions ----------
def generate(contents, system, json_mode=False):
    """Calls Gemini with retry + backup model. Returns (text, error)."""
    config = types.GenerateContentConfig(
        system_instruction=system,
        response_mime_type="application/json" if json_mode else None,
    )
    last_error = None
    for model in MODELS:
        for attempt in range(2):
            try:
                response = client.models.generate_content(
                    model=model, contents=contents, config=config
                )
                return response.text, None
            except Exception as e:
                last_error = e
                time.sleep(2)
    return None, last_error


def build_system_prompt():
    role = st.session_state.role
    level = st.session_state.level
    return (
        f"You are a friendly but professional interviewer conducting a job interview "
        f"for the role of {role}.\n"
        "Keep every reply short and clear: feedback in at most 3 short sentences, then one question.\n"
        f"Ask only ONE question at a time. Every question must be relevant to the {role} role.\n"
        f"Candidate level: {level}. {LEVELS[level]}"
    )


def ask_llm(messages, instruction):
    """Sends the interview so far to Gemini. Returns (reply, error)."""
    contents = [types.Content(role="user", parts=[types.Part(text="Start the interview.")])]
    for m in messages:
        role = "user" if m["role"] == "user" else "model"
        contents.append(types.Content(role=role, parts=[types.Part(text=m["content"])]))
    return generate(contents, build_system_prompt() + "\n\n" + instruction)


def generate_topics(role, level):
    """Asks Gemini for 4 interview topics for this role. Falls back to generic topics."""
    prompt = (
        f'List exactly 4 distinct interview topic areas for a "{role}" job interview, '
        f"suitable for a {level} candidate, ordered from fundamental to advanced. "
        "Each topic is a short phrase (max 6 words). "
        "Return only a JSON array of 4 strings."
    )
    text, error = generate(prompt, "You help plan job interviews.", json_mode=True)
    if error or not text:
        return FALLBACK_TOPICS
    try:
        clean = re.sub(r"^```(?:json)?|```$", "", text.strip(), flags=re.M).strip()
        topics = [str(t).strip() for t in json.loads(clean) if str(t).strip()][:4]
        return topics if len(topics) >= 2 else FALLBACK_TOPICS
    except Exception:
        return FALLBACK_TOPICS


def transcribe(audio_bytes):
    """Turns recorded speech into text. Returns (text, error)."""
    last_error = None
    for model in MODELS:
        try:
            response = client.models.generate_content(
                model=model,
                contents=[
                    types.Part.from_bytes(data=audio_bytes, mime_type="audio/wav"),
                    "Transcribe the speech in this audio exactly as spoken. "
                    "The speaker may have an Indian English accent. "
                    "Return only the transcribed text. If there is no speech, return NO_SPEECH.",
                ],
            )
            text = (response.text or "").strip()
            if text and text != "NO_SPEECH":
                return text, None
            last_error = "No speech detected in the recording"
        except Exception as e:
            last_error = e
            time.sleep(1)
    return None, last_error or "Empty transcription"


async def _edge_speak(text):
    communicate = edge_tts.Communicate(text, VOICE, rate="-5%")
    audio = b""
    async for chunk in communicate.stream():
        if chunk["type"] == "audio":
            audio += chunk["data"]
    return audio


def speak(text):
    """Converts text to speech. Returns mp3 bytes, or None if everything fails."""
    clean = re.sub(r"[*#_`]", "", text)   # remove markdown symbols

    # 1st choice: natural neural voice
    try:
        audio = asyncio.run(_edge_speak(clean))
        if audio:
            return audio
    except Exception:
        pass

    # Backup: basic gTTS voice
    try:
        buffer = io.BytesIO()
        gTTS(text=clean, lang="en", tld="co.in").write_to_fp(buffer)
        return buffer.getvalue()
    except Exception:
        return None


def reset_interview():
    for key in ["role", "level", "topics", "messages", "q_num", "finished", "audio_n", "audio_to_play"]:
        st.session_state.pop(key, None)
    st.rerun()


def handle_answer(answer):
    """Sends the candidate's answer to the AI and moves the interview forward."""
    with st.chat_message("user"):
        st.write(answer)

    role = st.session_state.role
    topics = st.session_state.topics
    history = st.session_state.messages + [{"role": "user", "content": answer}]

    if st.session_state.q_num < len(topics):
        is_last = False
        topic = topics[st.session_state.q_num]
        instruction = (
            "Give short feedback (2-3 lines) on the candidate's last answer. "
            f"Then ask ONE interview question about: {topic} (for a {role} candidate)."
        )
    else:
        is_last = True
        instruction = (
            "Give short feedback (2-3 lines) on the candidate's last answer. "
            f"Then write exactly {SUMMARY_MARKER} on its own line. "
            "After it, write a final summary with: an overall score out of 10, "
            f"2-3 strengths, and 2-3 things to improve for the {role} role."
        )

    with st.chat_message("assistant"):
        with st.spinner("Thinking..."):
            reply, error = ask_llm(history, instruction)

    if error:
        st.error("The AI is busy right now. Please send your answer again.")
    else:
        display_reply = reply
        voice_text = reply

        if is_last:
            st.session_state.finished = True
            feedback, marker, summary = reply.partition(SUMMARY_MARKER)
            if marker:
                display_reply = feedback.strip() + "\n\n---\n\n" + summary.strip()
                voice_text = feedback.strip()          # speak only the feedback
            else:
                voice_text = reply.split("\n\n")[0]    # fallback: first paragraph only
        else:
            st.session_state.q_num += 1

        st.session_state.messages = history + [{"role": "assistant", "content": display_reply}]
        if st.session_state.speak_on:
            st.session_state.audio_to_play = speak(voice_text)
        st.session_state.audio_n += 1   # resets the recorder for the next answer
        st.rerun()


# ---------- Page header ----------
st.title("AI Interview Assistant")
st.sidebar.checkbox("🔊 Read questions aloud", value=True, key="speak_on")

if "role" not in st.session_state:
    st.session_state.role = None

# ---------- Start screen: ask for the job role and level ----------
if st.session_state.role is None:
    st.write("Practice a mock interview for **any job role**.")
    with st.form("role_form"):
        role_input = st.text_input(
            "Which job role are you interviewing for?",
            placeholder="e.g. Data Analyst, AI Engineer, Web Developer, Accountant",
        )
        level_input = st.selectbox("Difficulty level", list(LEVELS))
        submitted = st.form_submit_button("Start interview")

    if submitted:
        role_clean = role_input.strip()[:80]
        if not role_clean:
            st.warning("Please type a job role first.")
        else:
            with st.spinner("Preparing your interview..."):
                topics = ["Introduction"] + generate_topics(role_clean, level_input)
                first_question = (
                    f"Hi! Welcome to your **{role_clean}** interview. "
                    "Let's begin: **Tell me about yourself.**"
                )
                st.session_state.role = role_clean
                st.session_state.level = level_input
                st.session_state.topics = topics
                st.session_state.messages = [{"role": "assistant", "content": first_question}]
                st.session_state.q_num = 1      # how many questions have been asked
                st.session_state.finished = False
                st.session_state.audio_n = 0    # changes the recorder's key to clear it
                st.session_state.audio_to_play = (
                    speak(first_question) if st.session_state.speak_on else None
                )
            st.rerun()
    st.stop()

# ---------- Interview screen ----------
total = len(st.session_state.topics)
st.sidebar.write(f"**Role:** {st.session_state.role}")
st.sidebar.write(f"**Level:** {st.session_state.level}")
if st.sidebar.button("🔄 Change role / restart"):
    reset_interview()

if st.session_state.finished:
    st.progress(1.0)
    st.caption("Interview complete")
else:
    st.progress(st.session_state.q_num / total)
    st.caption(f"Question {st.session_state.q_num} of {total}")

# Show chat history
for m in st.session_state.messages:
    with st.chat_message(m["role"]):
        st.write(m["content"])

# Play the interviewer's voice (once)
if st.session_state.audio_to_play and st.session_state.speak_on:
    st.audio(st.session_state.audio_to_play, format="audio/mp3", autoplay=True)
st.session_state.audio_to_play = None

# ---------- Interview logic ----------
if st.session_state.finished:
    if st.button("Start new interview"):
        reset_interview()
else:
    audio = st.audio_input(
        "🎤 Record your answer (or type below)",
        key=f"audio_{st.session_state.audio_n}",
    )
    typed = st.chat_input("Type your answer here...")

    if typed:
        handle_answer(typed)
    elif audio:
        audio_bytes = audio.getvalue()
        with st.spinner("Converting your speech to text..."):
            spoken_text, err = transcribe(audio_bytes)
        if spoken_text:
            handle_answer(spoken_text)
        else:
            st.error(f"Couldn't read your voice. Details: {err}")
            st.caption(f"Recording size: {len(audio_bytes) / 1024:.0f} KB")