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

BUFFER_SIZE = 4096
SEPARATOR = "<SEPARATOR>"
CHUNK_SEPARATOR = "<CHUNK_SEP>"
PORT = 5001
CHUNK_SERVER_PORT = 5002
METADATA_PORT = 5003

def send_file(filename):
    host = "0.0.0.0"

    file_path = get_file_path(filename)
    if not os.path.exists(file_path):
        print(f"[-] File not found: {file_path}")
        return

    # Get absolute paths for sent_files and chunks
    base_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "sent_files")
    chunk_dir = os.path.join(base_dir, "chunks")
    os.makedirs(chunk_dir, exist_ok=True)

    # Chunk the file
    metadata = chunk_file(file_path)

    # Save .nmeta metadata file
    save_nmeta_file(metadata, base_dir)
    print(f"[+] Generated metadata for {metadata['total_chunks']} chunks")

    # Save each chunk to disk before sending
    with open(file_path, "rb") as f:
        for chunk_info in metadata['chunks']:
            chunk_data = f.read(chunk_info['size'])
            chunk_hash = compute_chunk_hash(chunk_data)

            # Save chunk to disk so the chunk server can serve it
            save_chunk(chunk_hash, chunk_data, chunk_dir)
            print(f"[DEBUG] Saved chunk {chunk_info['index']} ({chunk_hash}) to disk")

    # Start metadata server
    def serve_metadata():
        meta_server = socket.socket()
        meta_server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        meta_server.bind((host, METADATA_PORT))
        meta_server.listen(5)
        print("[+] Metadata server listening on port", METADATA_PORT)
        while True:
            try:
                conn, addr = meta_server.accept()
                print(f"[+] Metadata request from {addr}")
                request = conn.recv(1024).decode().strip()
                if request == "GET_META":
                    conn.sendall(json.dumps(metadata).encode())
                else:
                    print(f"[!] Unknown metadata request: {request}")
                conn.close()
            except Exception as e:
                print(f"[!] Metadata server error: {e}")

    threading.Thread(target=serve_metadata, daemon=True).start()

    # Start file send server
    s = socket.socket()
    s.bind((host, PORT))
    s.listen(1)
    print(f"[+] Waiting for connection on port {PORT}...")

    client_socket, address = s.accept()
    print(f"[+] Connected to {address}")

    metadata_str = json.dumps(metadata)
    client_socket.send(f"{metadata_str}{SEPARATOR}".encode())

    with open(file_path, "rb") as f, tqdm(total=metadata['file_size'], unit="B", unit_scale=True) as progress:
        for chunk_info in metadata['chunks']:
            chunk_data = f.read(chunk_info['size'])
            chunk_hash = compute_chunk_hash(chunk_data)

            if chunk_hash != chunk_info['hash']:
                print(f"[-] Chunk {chunk_info['index']} hash mismatch!")
                continue

            chunk_header = f"{chunk_info['index']}{CHUNK_SEPARATOR}{chunk_info['hash']}{CHUNK_SEPARATOR}{chunk_info['size']}{SEPARATOR}"
            client_socket.send(chunk_header.encode())
            client_socket.sendall(chunk_data)
            progress.update(len(chunk_data))

    print(f"[+] File sent. Chunks are now available for serving on port {CHUNK_SERVER_PORT}")
    client_socket.close()
    s.close()


def handle_chunk_request(client_socket):
    try:
        request = b""
        while not request.endswith(b"\n"):
            part = client_socket.recv(1024)
            if not part:
                break
            request += part
        request = request.decode().strip()

        print(f"[DEBUG] Got chunk request: {request}")
        if request.startswith("GET_CHUNK"):
            _, chunk_hash = request.split()
            chunk_path = os.path.join("sent_files", "chunks", f"{chunk_hash}.chunk")
            print(f"[DEBUG] Looking for chunk file at: {chunk_path}")
            if os.path.exists(chunk_path):
                print(f"[DEBUG] Sending chunk {chunk_hash}")
                with open(chunk_path, 'rb') as f:
                    while True:
                        data = f.read(4096)
                        if not data:
                            break
                        client_socket.sendall(data)
            else:
                print(f"[DEBUG] ❌ Chunk not found: {chunk_path}")
                client_socket.sendall(b"CHUNK_NOT_FOUND\n")
    except Exception as e:
        print(f"[ERROR] Error handling chunk request: {e}")
    finally:
        client_socket.close()



def start_chunk_server():
    host = "0.0.0.0"
    s = socket.socket()
    s.bind((host, CHUNK_SERVER_PORT))
    s.listen(5)
    print(f"[+] Chunk server listening on port {CHUNK_SERVER_PORT}...")

    while True:
        client_socket, address = s.accept()
        threading.Thread(target=handle_chunk_request, args=(client_socket,)).start()

def get_metadata_from_peer(peer_ip):
    try:
        with socket.create_connection((peer_ip, METADATA_PORT), timeout=5) as s:
            s.sendall(b"GET_META")
            response = b""
            print("okokokkok")
            while True:
                data = s.recv(4096)
                if not data:
                    break
                response += data
            return json.loads(response.decode())
    except Exception as e:
        print(f"Failed to get metadata: {e}")
        return None

def download_chunk(peer, chunk):
    try:
        with socket.create_connection((peer, CHUNK_SERVER_PORT), timeout=5) as s:
            s.settimeout(5)  # <-- Add this
            s.sendall(f"GET_CHUNK {chunk['hash']}\n".encode())
            chunk_data = b""
            while len(chunk_data) < chunk['size']:
                try:
                    part = s.recv(min(BUFFER_SIZE, chunk['size'] - len(chunk_data)))
                    if not part:
                        print(f"[!] Connection closed early for chunk {chunk['index']}")
                        break  # prevent infinite loop
                    chunk_data += part
                except socket.timeout:
                    print(f"[!] Timeout while downloading chunk {chunk['index']}")
                    break

            if compute_chunk_hash(chunk_data) == chunk['hash']:
                with open(os.path.join("received_files", "chunks", f"{chunk['index']}.chunk"), "wb") as f:
                    f.write(chunk_data)
                return True
            else:
                print(f"[!] Hash mismatch for chunk {chunk['index']}")
    except Exception as e:
        print(f"[!] Error downloading chunk {chunk['index']} from {peer}: {e}")
    return False


def reconstruct_file(metadata):
    print("reconstruct starting")
    file_path = os.path.join("received_files", metadata['file_name'])
    with open(file_path, "wb") as f:
        for chunk in sorted(metadata['chunks'], key=lambda c: c['index']):
            chunk_file = os.path.join("received_files", "chunks", f"{chunk['index']}.chunk")
            if os.path.exists(chunk_file):
                with open(chunk_file, "rb") as cf:
                    f.write(cf.read())
    print("Came to reconstruct file:)")
    actual_hash = get_checksum(file_path)
    if actual_hash == metadata['file_hash']:
        print("[+] File hash matched. File reconstructed successfully.")
    else:
        print("[-] File hash mismatch! File may be corrupted.")

def download_from_multiple_peers(metadata, peers):
    print(f"[+] Downloading from {len(peers)} peers...")
    os.makedirs("received_files/chunks", exist_ok=True)
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
            try:
                if chunk['hash'] in downloaded:
                    print(f"[DEBUG] Chunk {chunk['index']} already downloaded — skipping")
                    continue

                success = False
                for peer in peers:
                    print(f"[DEBUG] Attempting to download chunk {chunk['index']} from {peer}")
                    if download_chunk(peer, chunk):
                        with lock:
                            downloaded.add(chunk['hash'])
                        print(f"[DEBUG] ✅ Successfully downloaded chunk {chunk['index']} from {peer}")
                        success = True
                        break

                if not success:
                    print(f"[ERROR] ❌ Failed to download chunk {chunk['index']} from any peer")

            except Exception as e:
                print(f"[ERROR] Worker crashed on chunk {chunk.get('index', '?')}: {e}")
            finally:
                chunk_queue.task_done()

    print("CAME HERE 1")
    threads = []
    for _ in range(min(4, len(peers) * 2)):
        t = threading.Thread(target=worker)
        t.start()
        threads.append(t)
    print("CAME HERE 2")
    chunk_queue.join()
    print("CAME HERE 3")
    for t in threads:
        t.join()
    print("CAME HERE 4")

    if len(downloaded) == len(metadata['chunks']):
        print("CAME HERE 5")
        reconstruct_file(metadata)
    else:
        print(f"[!] ❌ Missing {len(metadata['chunks']) - len(downloaded)} chunks")


def receive_file():
    sender_ip = input("Enter sender IP address: ").strip()
    metadata = get_metadata_from_peer(sender_ip)
    if not metadata:
        return
    use_multi = input("Use multiple peers? (y/n): ").lower() == 'y'
    if use_multi:
        peers = input("Enter peer IPs (comma separated): ").strip().split(',')
        download_from_multiple_peers(metadata, peers)
    else:
        download_from_multiple_peers(metadata, [sender_ip])

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--send', help="Send a file")
    parser.add_argument('--receive', action='store_true', help="Receive a file")
    parser.add_argument('--server', action='store_true', help="Start as chunk server")
    args = parser.parse_args()

    if args.send:
        send_file(args.send)
    elif args.receive:
        receive_file()
    elif args.server:
        start_chunk_server()
    else:
        print("Usage:")
        print("  --send <filename>  # Send a file")
        print("  --receive          # Receive a file")
        print("  --server           # Run as chunk server")

if __name__ == "__main__":
    main()