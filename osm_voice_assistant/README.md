# ScreenToSoundscapes OpenStreetMap Voice Assistant

A modular Python package that lets you **ask spoken or typed questions** about the world, **query OpenStreetMap**, **summarize results with LLaMA**, and **speak the answer back** using your cloned voice — now with multilingual support!

---

## ✨ Features

* 🎧 Voice input with Whisper (enter-to-start, silence-detect stop)
* 📄 Text or text-file input supported as alternatives
* 🌍 Natural language → Overpass QL generation (multi-language)
* 🧠 LLaMA summarization of OSM data (in English)
* 🌐 Auto-translation of summary back into original language
* 🗣️ Voice cloning with OpenVoice + MELo TTS
* ⚡ CLI, FastAPI server, or embeddable integration

---

## 📦 Installation

### 1. Clone and Install OpenVoice

```bash
git clone https://github.com/myshell-ai/OpenVoice.git
cd OpenVoice
pip install -e .
```

### 2. Download OpenVoice Checkpoints

```bash
curl -L -o checkpoints_v2_0417.zip \
  https://myshell-public-repo-host.s3.amazonaws.com/openvoice/checkpoints_v2_0417.zip

mkdir checkpoints_v2
unzip checkpoints_v2_0417.zip -d checkpoints_v2
rm checkpoints_v2_0417.zip
```

<details>
<summary>Windows (PowerShell)</summary>

```powershell
Invoke-WebRequest -Uri https://myshell-public-repo-host.s3.amazonaws.com/openvoice/checkpoints_v2_0417.zip `
  -OutFile checkpoints_v2_0417.zip
New-Item -ItemType Directory -Path checkpoints_v2
Expand-Archive -Path checkpoints_v2_0417.zip -DestinationPath checkpoints_v2
Remove-Item checkpoints_v2_0417.zip
```

</details>

---

### 3. (Optional) Download LLaMA Model

```bash
mkdir models
cd models
curl -L -o llama-2-7b-chat.Q4_K_M.gguf \
  https://huggingface.co/TheBloke/Llama-2-7B-Chat-GGUF/resolve/main/llama-2-7b-chat.Q4_K_M.gguf
```

---

### 4. Install Dependencies

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
  transformers \
  spacy \
  langdetect \
  deep-translator \
  geopy

python -m spacy download en_core_web_sm
```

> ⚠️ Also install Whisper CLI manually:
>
> ```bash
> pip install git+https://github.com/openai/whisper.git
> ```

---

### 5. System Requirements

* **PortAudio** (for `sounddevice`)

  * macOS: `brew install portaudio`
  * Ubuntu: `sudo apt install portaudio19-dev`
* **ffmpeg** (for `pydub`)

  * macOS: `brew install ffmpeg`
  * Ubuntu: `sudo apt install ffmpeg`

---

## 🗂️ Project Structure

```
osm_voice_assistant/
├── run_assistant.py            # 🔁 Main CLI assistant
├── utils/
│   ├── transcribe.py           # 🎤 Voice capture and Whisper transcription
│   ├── question_to_overpass.py # ❓ NLP parsing to Overpass QL
│   ├── overpass_to_osm.py      # 🌍 Run Overpass + LLaMA summarizer
│   ├── speak.py                # 🗣️ TTS with voice cloning
│   └── create_speaker.py       # 🧬 Generate speaker embeddings
├── models/                     # 🧠 LLaMA model (e.g., gguf)
└── checkpoints_v2/            # 🎙️ OpenVoice tone + SE embeddings
```

---

## 🚀 Usage

### 🎙️ Create Your Voice

```bash
python utils/create_speaker.py \
  --reference sample_audio/arnold_original.mp3 \
  --speaker-name arnold
```

Saves to:

```
checkpoints_v2/base_speakers/ses/arnold.pth
```

---

### 💬 Ask a Question

#### Via Voice (Whisper):

```bash
python run_assistant.py --speaker arnold
```

#### Via Text:

```bash
python run_assistant.py --speaker arnold --text "Où se trouve le marché aux puces à Paris ?"
```

#### Via File:

```bash
python run_assistant.py --speaker arnold --text-file input.txt
```

---

### 🧠 What Happens:

1. Transcribe or read question
2. Parse to Overpass QL
3. Fetch OSM results
4. Summarize with LLaMA (in English)
5. Translate summary back to original language (if needed)
6. Speak response with cloned voice

---

### 🌐 Run Server (Optional)

```bash
uvicorn server:app --reload
```

---

## 🧪 Example Commands

```bash
python run_assistant.py --speaker arnold --text "Where are the closest ATMs near King's Cross station?"
python run_assistant.py --speaker arnold --text "Y a-t-il des restaurants végétaliens à Lyon ?"
python run_assistant.py --speaker arnold --text "Où se trouve le marché aux puces à Paris ?"
```

---

## 🌍 Multilingual Support

* 🔎 Input:

  * Auto-detect language using `langdetect`
  * Translate to English for Overpass/LLaMA
* 🗣️ Output:

  * Summary auto-translated back to original language
  * TTS matches speaker + language

> ✅ Requires language-specific TTS support and voice samples.

---

## 🧰 Configurable

* Whisper model size: `transcribe.py`
* LLaMA model path: `overpass_to_osm.py`
* Summary language: auto-translated using `deep_translator`
* TTS output language: set via `--language` or inferred

---

## 🛑 Limitations

* LLaMA always responds in English → auto-translated
* Speaker voice must exist per language

---

## Coming Soon
