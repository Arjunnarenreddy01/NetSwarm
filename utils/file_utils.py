import os
import hashlib
import json
from pathlib import Path

BUFFER_SIZE = 4096
CHUNK_SIZE = 512 * 1024  # 512 KB

def get_checksum(filename, algorithm='sha256'):
    """Compute file checksum"""
    h = hashlib.new(algorithm)
    with open(filename, 'rb') as f:
        while chunk := f.read(BUFFER_SIZE):
            h.update(chunk)
    return h.hexdigest()

def compute_chunk_hash(data):
    """Compute SHA-256 hash of chunk data"""
    return hashlib.sha256(data).hexdigest()

def chunk_file(file_path):
    """Split file into chunks and compute hashes"""
    chunks = []
    file_hash = hashlib.sha256()
    chunk_index = 0
    
    with open(file_path, 'rb') as f:
        while True:
            chunk_data = f.read(CHUNK_SIZE)
            if not chunk_data:
                break
                
            chunk_hash = compute_chunk_hash(chunk_data)
            chunks.append({
                'index': chunk_index,
                'hash': chunk_hash,
                'size': len(chunk_data)
            })
            file_hash.update(chunk_data)
            chunk_index += 1
    
    return {
        'file_name': os.path.basename(file_path),
        'file_size': os.path.getsize(file_path),
        'file_hash': file_hash.hexdigest(),
        'total_chunks': len(chunks),
        'chunks': chunks
    }

def save_nmeta_file(metadata, output_dir):
    """Save metadata to .nmeta file"""
    os.makedirs(output_dir, exist_ok=True)
    nmeta_path = os.path.join(output_dir, f"{metadata['file_name']}.nmeta")
    with open(nmeta_path, 'w') as f:
        json.dump(metadata, f, indent=2)
    return nmeta_path

def get_file_path(filename):
    """Get absolute path for a file in sending_file/files_to_send"""
    project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    return os.path.join(project_root, 'sending_file', 'files_to_send', filename)