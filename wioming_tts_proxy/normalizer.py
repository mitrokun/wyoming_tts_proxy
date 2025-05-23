# --- START OF FILE normalizer.py ---
import logging
# import re # Если будете использовать re

_LOGGER = logging.getLogger(__name__)

class TextNormalizer:
    def __init__(self):
        _LOGGER.info("TextNormalizer initialized.")

    def normalize(self, text: str) -> str:
        if not text:
            return ""
        _LOGGER.debug(f"Original text for normalization: '{text}'")
        processed_text = text.replace("*", "")
        # processed_text = re.sub(r'\s+', ' ', processed_text).strip() # Пример
        _LOGGER.debug(f"Normalized text: '{processed_text}'")
        return processed_text
# --- END OF FILE normalizer.py ---