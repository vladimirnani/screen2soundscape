import os
import re
import glob
import torch
import argparse
import datetime
from openvoice.api import ToneColorConverter
from melo.api import TTS

import warnings
warnings.filterwarnings("ignore", category=UserWarning, module="openvoice")

CONVERTER_CKPT_DIR = "../checkpoints_v2/converter"
BASE_SE_DIR = "../checkpoints_v2/base_speakers/ses"
VOICES_DIR = "openvoice_voices"
DEFAULT_OUTPUT_DIR = "osm_assistant_speaker_audio"

device = "cuda:0" if torch.cuda.is_available() else "cpu"
tone_color_converter = ToneColorConverter(
    os.path.join(CONVERTER_CKPT_DIR, "config.json"),
    device=device
)
tone_color_converter.load_ckpt(
    os.path.join(CONVERTER_CKPT_DIR, "checkpoint.pth")
)

def speak(text: str, language: str, speaker_key: str, speed: float = 1.0, output_dir: str = DEFAULT_OUTPUT_DIR) -> str:
    os.makedirs(output_dir, exist_ok=True)

    language = language.upper()
    speaker_dir = os.path.join(VOICES_DIR, speaker_key)
    if not os.path.isdir(speaker_dir):
        raise FileNotFoundError(f"❌ Speaker directory not found: {speaker_dir}")

    # Search for appropriate audio file
    pattern = os.path.join(speaker_dir, f"{speaker_key}_{language}*.wav")
    matches = glob.glob(pattern)
    if not matches:
        raise FileNotFoundError(f"❌ No matching audio files found for speaker '{speaker_key}' and language '{language}'.")
    elif len(matches) > 1:
        print("⚠️ Multiple audio files found with that name, specify the source. For now I will use the full file by default.")

    src_audio_path = matches[0]

    # Load tone color embedding
    se_path = os.path.join(BASE_SE_DIR, f"{speaker_key}.pth")
    if not os.path.isfile(se_path):
        raise FileNotFoundError(f"❌ Missing speaker SE: {se_path}")

    target_se = torch.load(se_path, map_location=device)

    # Create base TTS audio
    model = TTS(language=language, device=device)
    speaker_ids = model.hps.data.spk2id
    if language.replace("_", "-") not in [k.upper().replace("_", "-") for k in speaker_ids.keys()]:
        raise ValueError(f"❌ No TTS model available for language '{language}'.")

    speaker_id = list(speaker_ids.values())[0]  # use any speaker id, audio will be replaced
    tmp_wav = os.path.join(output_dir, "tmp.wav")
    model.tts_to_file(text, speaker_id, tmp_wav, speed=speed)

    # Convert using voice cloning
    timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    out_path = os.path.join(output_dir, f"tts_{timestamp}.wav")
    tone_color_converter.convert(
        audio_src_path=tmp_wav,
        src_se=target_se,
        tgt_se=target_se,
        output_path=out_path,
        message="@MyShell"
    )

    try:
        os.remove(tmp_wav)
    except OSError:
        pass

    print(f"[speak] ✅ Saved cloned TTS to '{out_path}'")
    return out_path


if __name__ == "__main__":
    p = argparse.ArgumentParser(description="Generate cloned speech from text using OpenVoice + Melo TTS.")
    p.add_argument("text", help="The text to speak.")
    p.add_argument("--language", default="EN_NEWEST", help="Language/model key (e.g. EN_NEWEST, ES, FR, ...).")
    p.add_argument("--speaker", required=True, help="Speaker name (matches folder and SE file)")
    p.add_argument("--speed", type=float, default=1.0, help="Speech speed multiplier.")
    p.add_argument("--output-dir", default=DEFAULT_OUTPUT_DIR, help="Where to save the final WAV.")
    args = p.parse_args()

    speak(
        text=args.text,
        language=args.language,
        speaker_key=args.speaker,
        speed=args.speed,
        output_dir=args.output_dir
    )
