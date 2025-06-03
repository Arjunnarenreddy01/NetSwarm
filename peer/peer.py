import socket
import argparse
import os
import sys
import json
import threading
import shutil
import queue
from tqdm import tqdm

# Add project root to path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from utils.file_utils import (
    get_checksum,
    chunk_file,
    save_nmeta_file,
    compute_chunk_hash,
    get_file_path,
    save_chunk
)

# Constants
BUFFER_SIZE = 4096
SEPARATOR = "<SEPARATOR>"
CHUNK_SEPARATOR = "<CHUNK_SEP>"
PORT = 5001
CHUNK_SERVER_PORT = 5002
METADATA_PORT = 5003

# Paths
BASE_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "sent_files")
CHUNK_DIR = os.path.join(BASE_DIR, "chunks")
RECEIVED_DIR = os.path.join("received_files")
RECEIVED_CHUNKS = os.path.join(RECEIVED_DIR, "chunks")


def send_file(filename):
    host = "0.0.0.0"
    file_path = get_file_path(filename)
    if not os.path.exists(file_path):
        print(f"[-] File not found: {file_path}")
        return

    os.makedirs(CHUNK_DIR, exist_ok=True)
    metadata = chunk_file(file_path)
    save_nmeta_file(metadata, BASE_DIR)
    print(f"[+] Generated metadata for {metadata['total_chunks']} chunks")

    with open(file_path, "rb") as f:
        for chunk_info in metadata['chunks']:
            chunk_data = f.read(chunk_info['size'])
            chunk_hash = compute_chunk_hash(chunk_data)
            save_chunk(chunk_hash, chunk_data, CHUNK_DIR)
            print(f"[DEBUG] Saved chunk {chunk_info['index']} ({chunk_hash})")

    # Metadata Server Thread
    def serve_metadata():
        server = socket.socket()
        server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        server.bind((host, METADATA_PORT))
        server.listen(5)
        print(f"[+] Metadata server on port {METADATA_PORT}")
        while True:
            try:
                conn, addr = server.accept()
                print(f"[+] Metadata request from {addr}")
                request = conn.recv(1024).decode().strip()
                if request == "GET_META":
                    conn.sendall(json.dumps(metadata).encode())
                else:
                    print(f"[!] Unknown request: {request}")
                conn.close()
            except Exception as e:
                print(f"[!] Metadata server error: {e}")

    threading.Thread(target=serve_metadata, daemon=True).start()

    # Send file on PORT
    s = socket.socket()
    s.bind((host, PORT))
    s.listen(1)
    print(f"[+] Waiting for connection on port {PORT}...")
    client_socket, address = s.accept()
    print(f"[+] Connected to {address}")

    client_socket.send(f"{json.dumps(metadata)}{SEPARATOR}".encode())

    with open(file_path, "rb") as f, tqdm(total=metadata['file_size'], unit="B", unit_scale=True) as progress:
        for chunk_info in metadata['chunks']:
            chunk_data = f.read(chunk_info['size'])
            if compute_chunk_hash(chunk_data) != chunk_info['hash']:
                print(f"[-] Hash mismatch for chunk {chunk_info['index']} — skipping")
                continue
            header = f"{chunk_info['index']}{CHUNK_SEPARATOR}{chunk_info['hash']}{CHUNK_SEPARATOR}{chunk_info['size']}{SEPARATOR}"
            client_socket.send(header.encode())
            client_socket.sendall(chunk_data)
            progress.update(len(chunk_data))

    print(f"[+] File sent. Chunks available on port {CHUNK_SERVER_PORT}")
    client_socket.close()
    s.close()


def handle_chunk_request(client_socket):
    try:
        request = b""
        while not request.endswith(b"\r\n\r\n"):
            data = client_socket.recv(1)
            if not data:
                break
            request += data
        
        if not request:
            return
            
        request = request.decode().strip()
        if request.startswith("GET_CHUNK"):
            _, chunk_hash = request.split()
            chunk_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "sent_files", "chunks")
            chunk_path = os.path.join(chunk_dir, f"{chunk_hash}.chunk")
            
            print(f"[DEBUG] Looking for chunk at: {chunk_path}")
            
            if os.path.exists(chunk_path):
                print(f"[+] Sending chunk {chunk_hash}")
                with open(chunk_path, 'rb') as f:
                    while True:
                        data = f.read(4096)
                        if not data:
                            break
                        client_socket.sendall(data)
            else:
                print(f"[!] Chunk not found at {chunk_path}")
                client_socket.sendall(b"CHUNK_NOT_FOUND\r\n\r\n")
    except Exception as e:
        print(f"[!] Error handling request: {e}")
    finally:
        client_socket.close()



def start_chunk_server():
    host = "0.0.0.0"
    s = socket.socket()
    s.bind((host, CHUNK_SERVER_PORT))
    s.listen(5)
    print(f"[+] Chunk server listening on port {CHUNK_SERVER_PORT}...")
    while True:
        client_socket, _ = s.accept()
        threading.Thread(target=handle_chunk_request, args=(client_socket,), daemon=True).start()


def get_metadata_from_peer(peer_ip):
    try:
        with socket.create_connection((peer_ip, METADATA_PORT), timeout=5) as s:
            s.sendall(b"GET_META")
            response = b""
            while True:
                data = s.recv(4096)
                if not data:
                    break
                response += data
            return json.loads(response.decode())
    except Exception as e:
        print(f"[-] Failed to get metadata: {e}")
        return None


def download_chunk(peer, chunk):
    try:
        ip, port = peer.split(":") if ":" in peer else (peer, CHUNK_SERVER_PORT)
        with socket.create_connection((ip, int(port)), timeout=5) as s:
            s.sendall(f"GET_CHUNK {chunk['hash']}\r\n\r\n".encode())

            chunk_data = bytearray()
            while True:
                data = s.recv(BUFFER_SIZE)
                if not data:
                    break
                if data.startswith(b"CHUNK_NOT_FOUND") or data.startswith(b"ERROR"):
                    return False
                chunk_data.extend(data)

            if len(chunk_data) != chunk['size'] or compute_chunk_hash(chunk_data) != chunk['hash']:
                return False

            os.makedirs(RECEIVED_CHUNKS, exist_ok=True)
            with open(os.path.join(RECEIVED_CHUNKS, f"{chunk['hash']}.chunk"), "wb") as f:
                f.write(chunk_data)

            return True
    except Exception as e:
        print(f"[!] Error downloading chunk {chunk['index']}: {e}")
    return False



def reconstruct_file(metadata):
    print("[*] Reconstructing file...")
    file_path = os.path.join(RECEIVED_DIR, metadata['file_name'])
    with open(file_path, "wb") as f:
        for chunk in sorted(metadata['chunks'], key=lambda c: c['index']):
            path = os.path.join(RECEIVED_CHUNKS, f"{chunk['hash']}.chunk")
            if os.path.exists(path):
                with open(path, "rb") as cf:
                    f.write(cf.read())
    if get_checksum(file_path) == metadata['file_hash']:
        print("[+] File reconstructed successfully.")
    else:
        print("[-] Hash mismatch. Reconstruction may be corrupted.")


def download_from_multiple_peers(metadata, peers):
    os.makedirs(RECEIVED_CHUNKS, exist_ok=True)
    chunk_queue = queue.Queue()
    for chunk in metadata['chunks']:
        chunk_queue.put(chunk)

    downloaded = set()
    lock = threading.Lock()

    def worker():
        while True:
            try:
                chunk = chunk_queue.get_nowait()
            except queue.Empty:
                break
            if chunk['hash'] in downloaded:
                continue
            for peer in peers:
                if download_chunk(peer, chunk):
                    with lock:
                        downloaded.add(chunk['hash'])
                    break
            chunk_queue.task_done()

    threads = [threading.Thread(target=worker) for _ in range(min(4, len(peers) * 2))]
    for t in threads:
        t.start()
    chunk_queue.join()
    for t in threads:
        t.join()

    if len(downloaded) == len(metadata['chunks']):
        reconstruct_file(metadata)
    else:
        print(f"[-] Missing {len(metadata['chunks']) - len(downloaded)} chunks.")


def receive_file():
    sender_ip = input("Enter sender IP: ").strip()
    metadata = get_metadata_from_peer(sender_ip)
    if not metadata:
        return
    if input("Use multiple peers? (y/n): ").strip().lower() == 'y':
        peers = input("Enter peer IPs (comma-separated): ").strip().split(',')
        download_from_multiple_peers(metadata, peers)
    else:
        download_from_multiple_peers(metadata, [sender_ip])


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--send', help="Send a file")
    parser.add_argument('--receive', action='store_true', help="Receive a file")
    parser.add_argument('--server', action='store_true', help="Run chunk server")
    args = parser.parse_args()

    if args.send:
        send_file(args.send)
    elif args.receive:
        receive_file()
    elif args.server:
        start_chunk_server()
    else:
        print("Usage:\n  --send <filename>\n  --receive\n  --server")

if __name__ == "__main__":
    main()
