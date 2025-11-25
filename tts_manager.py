import requests
import json
import base64
from playsound import playsound
import tempfile
import os

# --- Configuration ---
# IMPORTANT: Paste your Google Cloud API Key here.
# Do NOT commit this key to public source control (like GitHub).
API_KEY = "AIzaSyDCnhSSeHOWpEM9XCQ4d87d-7Wlkoicx7o"

TTS_URL = f"https://texttospeech.googleapis.com/v1/text:synthesize?key={API_KEY}"

class TTSManager:
    def __init__(self, master_config_path='framework/Jarvis_Engine_Master.json'):
        """
        Initializes the Text-to-Speech engine.
        """
        self.personas_config = self._load_personas_config(master_config_path)

    def _load_personas_config(self, path):
        """Loads the persona voice configurations from the master JSON file."""
        try:
            with open(path, 'r', encoding='utf-8') as f:
                data = json.load(f)
            return {p['name']: p.get('voice_tags', []) for p in data['jarvis_engine']['personas']}
        except (FileNotFoundError, KeyError):
            return {}

    def speak(self, text, persona_name=None):
        """
        Converts text to speech using Google Cloud TTS with an API key.
        """
        if not API_KEY or API_KEY == "YOUR_GOOGLE_CLOUD_API_KEY":
            print("TTSManager ERROR: Google Cloud API Key is not set in tts_manager.py.")
            return

        headers = {"Content-Type": "application/json"}

        # Basic voice configuration. This can be expanded later to use voice_tags.
        # For a list of voices, see: https://cloud.google.com/text-to-speech/docs/voices
        voice_config = {
            "languageCode": "en-US",
            "name": "en-US-Studio-M" # A high-quality, standard male voice.
        }

        data = {
            "input": {"text": text},
            "voice": voice_config,
            "audioConfig": {"audioEncoding": "MP3"}
        }

        try:
            response = requests.post(TTS_URL, headers=headers, data=json.dumps(data))
            response.raise_for_status()
            response_json = response.json()

            # Check if the 'audioContent' key exists in the response
            if 'audioContent' not in response_json:
                print(f"TTSManager ERROR: 'audioContent' not found in API response. Response: {response_json}")
                return

            audio_data = base64.b64decode(response_json['audioContent'])

            # Create a temporary file to play the audio from
            with tempfile.NamedTemporaryFile(delete=False, suffix=".mp3") as tmp_audio_file:
                tmp_audio_file.write(audio_data)
                tmp_file_name = tmp_audio_file.name

            try:
                playsound(tmp_file_name)
            finally:
                os.remove(tmp_file_name) # Clean up the temporary file after playing

        except requests.exceptions.RequestException as e:
            print(f"TTSManager ERROR: Failed to call Google TTS API: {e}")
        except Exception as e:
            print(f"TTSManager ERROR: Failed to decode or play audio: {e}")