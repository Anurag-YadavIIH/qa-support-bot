# app/utils.py
import os
os.environ["ANONYMIZED_TELEMETRY"] = "false"   # silence ChromaDB telemetry

import os
from dotenv import load_dotenv

load_dotenv()

def get_env(key: str, default: str = None) -> str:
    value = os.getenv(key, default)
    if value is None:
        raise ValueError(f"Missing required environment variable: {key}")
    return value

TARGET_URL        = get_env("TARGET_URL")
MAX_PAGES         = int(get_env("MAX_PAGES", "10"))
CHROMA_COLLECTION = get_env("CHROMA_COLLECTION", "support_bot")

# REPLACED: OLLAMA_MODEL, OLLAMA_HOST
OPENAI_API_KEY = get_env("OPENAI_API_KEY")
OPENAI_MODEL   = get_env("OPENAI_MODEL", "gpt-4o-mini")