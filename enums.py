from enum import Enum, auto

class PeerStatus(Enum):
    CONNECTED = auto()
    DISCONNECTED = auto()
    UNKNOWN = auto()

class MessageType(Enum):
    HANDSHAKE = auto()
    FILE_REQUEST = auto()
    FILE_CHUNK = auto()
    FILE_METADATA = auto()
    HEARTBEAT = auto()
    PEER_LIST = auto()
