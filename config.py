import os
from pathlib import Path
from dotenv import load_dotenv

# Load .env
BASE_DIR = Path(__file__).resolve().parent
load_dotenv(BASE_DIR / ".env")

GOOGLE_API_KEY = os.getenv("GOOGLE_API_KEY", "")
GOOGLE_MODEL = os.getenv("GOOGLE_MODEL", "gemini-3.5-flash-lite")
GOOGLE_EMBEDDING_MODEL = os.getenv("GOOGLE_EMBEDDING_MODEL", "models/gemini-embedding-001")

CHROMA_PERSIST_DIR = str(BASE_DIR / os.getenv("CHROMA_PERSIST_DIR", "./chroma_db"))
SQLITE_DB_PATH = str(BASE_DIR / os.getenv("SQLITE_DB_PATH", "leads.db"))
DATA_DIR = str(BASE_DIR / "data")

# Similarity score threshold for RAG (lower distance = higher similarity in Chroma L2/cosine)
# For Chroma with cosine distance, distance < 0.65 or similarity > 0.35 is relevant
RAG_DISTANCE_THRESHOLD = float(os.getenv("RAG_DISTANCE_THRESHOLD", "0.65"))
TOP_K_RESULTS = int(os.getenv("TOP_K_RESULTS", "4"))
