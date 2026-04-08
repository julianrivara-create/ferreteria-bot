import os
import logging
from typing import Optional
from openai import OpenAI
from bot_sales.config import Config

class AudioTranscriber:
    """
    Transcribes audio using OpenAI's Whisper model via API.
    """
    
    def __init__(self):
        self.logger = logging.getLogger(__name__)
        self.client = None
        
        if Config.OPENAI_API_KEY:
            try:
                self.client = OpenAI(api_key=Config.OPENAI_API_KEY)
            except Exception as e:
                self.logger.error(f"Failed to init OpenAI client for audio: {e}")
        else:
            self.logger.warning("OpenAI API Key missing. Audio transcription disabled.")

    def transcribe(self, file_path: str) -> Optional[str]:
        """
        Transcribes an audio file to text.
        
        Args:
            file_path: Path to the audio file on disk
            
        Returns:
            Transcribed text or None if failed
        """
        if not self.client:
            self.logger.error("Transcriber requested but client not initialized")
            return None
            
        if not os.path.exists(file_path):
            self.logger.error(f"Audio file not found: {file_path}")
            return None
            
        try:
            self.logger.info(f"Transcribing audio file: {file_path}")
            
            with open(file_path, "rb") as audio_file:
                transcript = self.client.audio.transcriptions.create(
                    model="whisper-1", 
                    file=audio_file,
                    response_format="text"
                )
                
            self.logger.info(f"Transcription result: {transcript[:50]}...")
            return transcript
            
        except Exception as e:
            self.logger.error(f"Transcription failed: {e}")
            return None
