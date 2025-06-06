from dataclasses import dataclass, field
from typing import List
from uuid import uuid4
import time

@dataclass
class PeerInfo:
    peer_id: str
    ip: str
    port: int
    status: str  # Could be str or PeerStatus

@dataclass
class FileMetadata:
    file_id: str = field(default_factory=lambda: str(uuid4()))
    filename: str = ""
    size: int = 0
    chunks: int = 0
    hash_list: List[str] = field(default_factory=list)
    created_at: float = field(default_factory=time.time)
