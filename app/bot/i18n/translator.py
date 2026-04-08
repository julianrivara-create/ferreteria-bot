import json
import os
import logging
from typing import Dict, Optional

class Translator:
    """
    Sistema de internacionalización (i18n)
    Soporta español e inglés
    """
    
    def __init__(self, default_locale: str = 'es'):
        self.default_locale = default_locale
        self.current_locale = default_locale
        self.translations = {}
        
        # Cargar traducciones
        self._load_translations()
    
    def _load_translations(self):
        """Carga archivos de traducción"""
        base_dir = os.path.dirname(__file__)
        
        for locale in ['es', 'en']:
            file_path = os.path.join(base_dir, f'{locale}.json')
            if os.path.exists(file_path):
                try:
                    with open(file_path, 'r', encoding='utf-8') as f:
                        self.translations[locale] = json.load(f)
                except Exception as e:
                    logging.error(f"Error loading {locale}.json: {e}")
                    self.translations[locale] = {}
            else:
                self.translations[locale] = {}
    
    def detect_language(self, text: str) -> str:
        """
        Detecta idioma del mensaje (simple heurística)
        
        Returns:
            'es' o 'en'
        """
        text_lower = text.lower()
        
        # Keywords en español
        es_keywords = ['hola', 'qué', 'cómo', 'cuánto', 'tenés', 'querés', 
                       'soy', 'estoy', 'necesito', 'busco', 'gracias']
        
        # Keywords en inglés
        en_keywords = ['hello', 'hi', 'what', 'how', 'much', 'want', 
                       'need', 'looking', 'thanks', 'thank']
        
        es_count = sum(1 for kw in es_keywords if kw in text_lower)
        en_count = sum(1 for kw in en_keywords if kw in text_lower)
        
        if en_count > es_count:
            return 'en'
        
        return 'es'  # Default español
    
    def set_locale(self, locale: str):
        """Establece idioma actual"""
        if locale in self.translations:
            self.current_locale = locale
            logging.info(f"Locale set to: {locale}")
        else:
            logging.warning(f"Locale {locale} not found, using {self.default_locale}")
    
    def get(self, key: str, locale: Optional[str] = None, **kwargs) -> str:
        """
        Obtiene traducción
        
        Args:
            key: Clave de traducción
            locale: Idioma (opcional, usa current_locale si no se especifica)
            **kwargs: Variables para formatear el string
        
        Returns:
            String traducido
        """
        loc = locale or self.current_locale
        
        # Intenta obtener traducción
        translation = self.translations.get(loc,  {}).get(key)
        
        # Fallback a default locale
        if translation is None:
            translation = self.translations.get(self.default_locale, {}).get(key)
        
        # Fallback a la key misma
        if translation is None:
            logging.warning(f"Translation not found for key: {key}")
            return key
        
        # Formatear con variables si existen
        if kwargs:
            try:
                return translation.format(**kwargs)
            except:
                return translation
        
        return translation
    
    def translate_batch(self, keys: list, locale: Optional[str] = None) -> Dict[str, str]:
        """
        Traduce múltiples keys de una vez
        
        Returns:
            {key: translation}
        """
        return {key: self.get(key, locale) for key in keys}
