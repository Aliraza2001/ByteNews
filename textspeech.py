from textspeech import gTTS
import os

def generate_tts(text, output_path):
    tts = gTTS(text=text, lang='en')
    tts.save(output_path)