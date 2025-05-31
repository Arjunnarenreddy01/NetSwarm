import hashlib

BUFFER_SIZE = 4096

def get_checksum(file_path):
    sha256 = hashlib.sha256()
    with open(file_path, "rb") as f:
        while chunk := f.read(BUFFER_SIZE):
            sha256.update(chunk)
    return sha256.hexdigest()
