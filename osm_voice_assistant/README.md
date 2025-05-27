````markdown
# OSM Voice Assistant

A modular Python package that lets you **ask spoken questions** about the world, **query OpenStreetMap**, **summarize** the results via LLaMA, and **speak the answer back** in your cloned voice.

## ✨ Features

- 🎙️ **Voice input** with OpenAI Whisper (Enter to start/stop + silence detection)
- 🌍 **Natural language → Overpass API** mapping + OSM data fetch
- 🧠 **LLaMA summarization** of raw OSM results
- 🗣️ **Voice cloning & TTS** with OpenVoice + MELo
- ⚡ CLI, HTTP (FastAPI), and browser/desktop integration

---

## 📦 Installation

### 1. Clone the Repo & Install OpenVoice

```bash
git clone git@github.com:myshell-ai/OpenVoice.git
cd OpenVoice
pip install -e .
````

### 2. Download the OpenVoice Checkpoints

```bash
curl -L -o checkpoints_v2_0417.zip \
  https://myshell-public-repo-host.s3.amazonaws.com/openvoice/checkpoints_v2_0417.zip

mkdir checkpoints_v2
unzip checkpoints_v2_0417.zip -d checkpoints_v2
rm checkpoints_v2_0417.zip
```

<details>
<summary><strong>Windows (PowerShell)</strong> version</summary>

```powershell
Invoke-WebRequest -Uri https://myshell-public-repo-host.s3.amazonaws.com/openvoice/checkpoints_v2_0417.zip `
  -OutFile checkpoints_v2_0417.zip
New-Item -ItemType Directory -Path checkpoints_v2
Expand-Archive -Path checkpoints_v2_0417.zip -DestinationPath checkpoints_v2
Remove-Item checkpoints_v2_0417.zip
```

</details>

### 3. (Optional) Download LLaMA Model

```bash
mkdir models
cd models
curl -L -o llama-2-7b-chat.Q4_K_M.gguf \
  https://huggingface.co/TheBloke/Llama-2-7B-Chat-GGUF/resolve/main/llama-2-7b-chat.Q4_K_M.gguf
```

### 4. Install Python Dependencies

```bash
pip install \
  openai-whisper \
  webrtcvad \
  sounddevice \
  scipy \
  numpy \
  pydub \
  overpy \
  requests \
  llama-cpp-python \
  transformers
```

> 🔧 Also install Whisper CLI manually:
>
> ```bash
> pip install git+https://github.com/openai/whisper.git
> ```

### 5. System Requirements

* **PortAudio** (for `sounddevice`)

  * macOS: `brew install portaudio`
  * Ubuntu/Debian: `sudo apt-get install portaudio19-dev`
* **ffmpeg** (for MP3 processing with `pydub`)

  * macOS: `brew install ffmpeg`
  * Ubuntu/Debian: `sudo apt-get install ffmpeg`

---

## 🗂️ Project Structure

```
osm_voice_assistant/
├── run_assistant.py              # Main script to run the assistant
├── utils/
│   ├── __init__.py
│   ├── transcribe.py             # Record + transcribe speech to text
│   ├── question_to_overpass.py   # Natural language → Overpass API
│   ├── overpass_to_osm.py        # Fetch and summarize OSM data
│   ├── speak.py                  # TTS and voice cloning
│   └── create_speaker.py         # Extract speaker embedding from reference audio
```

---

## 🚀 Usage

### 1. Create Your Own Voice (Speaker Embedding)

Provide a reference voice clip and generate a speaker embedding:

```bash
python utils/create_speaker.py \
  --reference sample_audio/arnold_original.mp3 \
  --speaker-name arnold
```

This saves a speaker embedding as:

```
checkpoints_v2/base_speakers/ses/arnold.pth
```

You can now use this voice in the assistant.

---

### 2. Run the CLI Assistant

```bash
python run_assistant.py
```

1. Press **Enter** to start speaking your question.
2. Press **Enter again** or pause to stop.
3. The assistant will:

   * Transcribe audio using Whisper
   * Translate the question → Overpass API query
   * Fetch OSM data and summarize via LLaMA
   * Speak the result in your cloned voice

---

### 3. Run the FastAPI Server

Example server code (`server.py`):

```python
from fastapi import FastAPI
from utils.transcribe import record_and_transcribe
from utils.question_to_overpass import parse_question_to_overpass
from utils.overpass_to_osm import summarize_osm_results
from utils.speak import speak

app = FastAPI()

@app.get("/ask")
async def ask():
    question, lang = record_and_transcribe()
    osm_json = parse_question_to_overpass(question)
    summary = summarize_osm_results(osm_json)
    speak(summary)
    return {"question": question, "summary": summary}
```

Run:

```bash
uvicorn server:app --reload
```

Then access it via:

```bash
http://localhost:8000/ask
```

---

## ⚙️ Configuration

* Whisper model size: `transcribe.py` → `whisper.load_model("base")`
* LLaMA model path: set `LLAMA_MODEL_PATH` in `overpass_to_osm.py`
* Output folders: change defaults in `transcribe.py`, `speak.py`, etc.
* Supported speaker languages: check `spk2id` in `speak.py`

---

## 🪪 License

MIT © Your Name or Organization
Feel free to fork, adapt, and contribute via GitHub!

```
To Do: version split into multiple language variants (e.g. French) or want badges (e.g. for Python version, license, etc.).
```

