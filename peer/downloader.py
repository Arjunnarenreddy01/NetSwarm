import socket
import threading
import queue
import time
from typing import Dict, List
from pathlib import Path
from utils.file_utils import compute_chunk_hash, save_chunk, reconstruct_file

class ChunkDownloader:
    def __init__(self, metadata, peers: List[str], chunk_dir: str):
        self.metadata = metadata
        self.peers = peers
        self.chunk_dir = chunk_dir
        self.download_queue = queue.Queue()
        self.lock = threading.Lock()
        self.downloaded_chunks = set()
        self.failed_chunks = set()
        
        # Initialize download queue with all chunks
        for chunk in metadata['chunks']:
            self.download_queue.put(chunk['hash'])
    
    def request_chunk(self, peer: str, chunk_hash: str) -> bytes:
        """Request a single chunk from a peer"""
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                s.settimeout(5.0)
                s.connect((peer, 5001))
                
                # Send chunk request
                request = f"GET_CHUNK {chunk_hash}\r\n\r\n"
                s.sendall(request.encode())
                
                # Receive response
                response = b""
                while True:
                    data = s.recv(4096)
                    if not data:
                        break
                    response += data
                
                if response.startswith(b"CHUNK_NOT_FOUND"):
                    return None
                
                return response
        except Exception as e:
            print(f"Error requesting chunk from {peer}: {e}")
            return None
    
    def worker(self):
        """Worker thread that processes download queue"""
        while True:
            chunk_hash = self.download_queue.get()
            if chunk_hash is None:  # Sentinel value to stop worker
                self.download_queue.task_done()
                break
            
            # Skip if already downloaded
            with self.lock:
                if chunk_hash in self.downloaded_chunks:
                    self.download_queue.task_done()
                    continue
            
            # Try each peer until successful
            for peer in self.peers:
                chunk_data = self.request_chunk(peer, chunk_hash)
                if chunk_data is None:
                    continue
                
                # Verify chunk hash
                if compute_chunk_hash(chunk_data) != chunk_hash:
                    print(f"Hash mismatch for chunk {chunk_hash}")
                    continue
                
                # Save chunk
                try:
                    save_chunk(chunk_hash, chunk_data, self.chunk_dir)
                    with self.lock:
                        self.downloaded_chunks.add(chunk_hash)
                    print(f"Successfully downloaded chunk {chunk_hash[:8]}...")
                    break
                except Exception as e:
                    print(f"Error saving chunk {chunk_hash}: {e}")
            
            self.download_queue.task_done()
    
    def start_download(self, num_workers=4):
        """Start parallel download with specified number of workers"""
        threads = []
        for _ in range(num_workers):
            t = threading.Thread(target=self.worker)
            t.start()
            threads.append(t)
        
        # Wait for all chunks to be processed
        self.download_queue.join()
        
        # Stop workers
        for _ in range(num_workers):
            self.download_queue.put(None)
        for t in threads:
            t.join()
        
        # Check if all chunks were downloaded
        missing_chunks = [
            chunk for chunk in self.metadata['chunks']
            if chunk['hash'] not in self.downloaded_chunks
        ]
        
        if missing_chunks:
            print(f"Failed to download {len(missing_chunks)} chunks")
            return False
        
        # Reconstruct file
        output_path = os.path.join(os.path.dirname(self.chunk_dir), self.metadata['file_name'])
        try:
            reconstruct_file(self.metadata, self.chunk_dir, output_path)
            print(f"Successfully reconstructed file at {output_path}")
            return True
        except Exception as e:
            print(f"Error reconstructing file: {e}")
            return False