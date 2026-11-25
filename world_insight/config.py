import os
from dataclasses import dataclass, field
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[1]


@dataclass
class Settings:
    api_key: str = field(default="", repr=False)
    base_url: str = "https://gms.ssafy.io/gmsapi/api.openai.com/v1"
    model: str = "gpt-6-luna"
    embedding_model: str = "text-embedding-3-small"
    wiki_contact: str = field(default="", repr=False)
    chroma_dir: str = str(ROOT / "storage/chroma")
    chunk_size: int = 1000
    chunk_overlap: int = 200
    top_k: int = 4
    fetch_k: int = 20
    lambda_mult: float = 0.5
    wiki_interval: float = 0.7
    wiki_max_requests: int = 200
    timeout: float = 60

    def __post_init__(self):
        if not 0 <= self.chunk_overlap < self.chunk_size:
            raise ValueError("chunk_overlap must be smaller than chunk_size")
        if not 1 <= self.top_k <= self.fetch_k or not 0 <= self.lambda_mult <= 1:
            raise ValueError("Invalid retrieval settings")

    @classmethod
    def load(cls):
        load_dotenv(ROOT / ".env")
        return cls(
            api_key=os.getenv("OPENAI_API_KEY") or os.getenv("GMS_KEY", ""),
            base_url=os.getenv("OPENAI_BASE_URL", cls.base_url),
            model=os.getenv("OPENAI_MODEL", cls.model),
            embedding_model=os.getenv("EMBEDDING_MODEL", cls.embedding_model),
            wiki_contact=os.getenv("WIKI_CONTACT", ""),
            chroma_dir=str(ROOT / os.getenv("CHROMA_DIR", "storage/chroma")),
            chunk_size=int(os.getenv("CHUNK_SIZE", 1000)),
            chunk_overlap=int(os.getenv("CHUNK_OVERLAP", 200)),
            top_k=int(os.getenv("TOP_K", 4)),
            fetch_k=int(os.getenv("FETCH_K", 20)),
            lambda_mult=float(os.getenv("MMR_LAMBDA", 0.5)),
            wiki_interval=float(os.getenv("WIKI_INTERVAL", 0.7)),
            wiki_max_requests=int(os.getenv("WIKI_MAX_REQUESTS", 200)),
            timeout=float(os.getenv("API_TIMEOUT", 60)),
        )
