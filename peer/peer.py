import socket
import argparse
import os
import sys
import json
import threading
import requests
import queue
from tqdm import tqdm
import atexit

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

def get_free_port():
    s = socket.socket()
    s.bind(('', 0))
    port = s.getsockname()[1]
    s.close()
    return port


def select_peer(peers):
    if not peers:
        return None
    peer_keys = list(peers.keys())
    print("\nSelect a peer by index:")
    for idx, peer_id in enumerate(peer_keys):
        print(f"{idx}: {peer_id} @ {peers[peer_id]['ip']}:{peers[peer_id]['port']}")
    choice = int(input("Enter index: "))
    return {
        "ip": peers[peer_keys[choice]]['ip'],
        "chunk_port": peers[peer_keys[choice]]['chunk_port']
    }


def get_available_peers():
    try:
        res = requests.get("http://localhost:8000/peers")
        if res.status_code == 200:
            peers = res.json()
            if not peers:
                print("No peers are currently registered.")
                return {}
            print("Available Peers:")
            for peer_id, info in peers.items():
                print(f"- {peer_id} @ {info['ip']}:{info['port']}")
                print(f"  Chunk Port: {info['chunk_port']}")
                print(f"  Files: {', '.join(info['files'])}")
            return peers
        else:
            print("Failed to fetch peers from bootstrap server.")
            return {}
    except Exception as e:
        print(f"[!] Error fetching peers: {e}")
        return {}



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

    # Start chunk server
    chunk_server_port = get_free_port()
    global CHUNK_SERVER_PORT
    CHUNK_SERVER_PORT = chunk_server_port

    threading.Thread(target=start_chunk_server, args=(chunk_server_port,), daemon=True).start()
    print(f"[+] Started chunk server on port {chunk_server_port}")
    
    metadata_port = get_free_port()
    # if os.path.exists(CHUNK_DIR):
    #     for f in os.listdir(CHUNK_DIR):
    #         os.remove(os.path.join(CHUNK_DIR, f))
    # Save chunks
    with open(file_path, "rb") as f:
        for chunk_info in metadata['chunks']:
            chunk_data = f.read(chunk_info['size'])
            chunk_hash = compute_chunk_hash(chunk_data)
            save_chunk(chunk_hash, chunk_data, CHUNK_DIR)
            print(f"[DEBUG] Saved chunk {chunk_info['index']} ({chunk_hash})")

    # Metadata server thread
    def serve_metadata():
        server = socket.socket()
        server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        server.bind((host, metadata_port))
        server.listen(5)
        print(f"[+] Metadata server on port {metadata_port}")
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

    # Cleanup on exit
    def cleanup():
        try:
            if os.path.exists(file_path):
                os.remove(file_path)
                print(f"[CLEANUP] Removed original file: {file_path}")
            meta_file = os.path.join(BASE_DIR, f"{filename}.nmeta")
            if os.path.exists(meta_file):
                os.remove(meta_file)
                print(f"[CLEANUP] Removed metadata file: {meta_file}")
            for f in os.listdir(CHUNK_DIR):
                os.remove(os.path.join(CHUNK_DIR, f))
            print(f"[CLEANUP] Removed all chunk files from {CHUNK_DIR}")
        except Exception as e:
            print(f"[!] Cleanup failed: {e}")

    atexit.register(cleanup)

    # Prepare to send file directly
    PORT = get_free_port()
    s = socket.socket()
    s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    s.bind((host, PORT))
    s.listen(1)
    print(f"[+] Waiting for connection on port {PORT}...")

    # Register with Bootstrap Server
    try:
        peer_id = f"peer_{PORT}"
        bootstrap_url = "http://localhost:8000/register"

        payload = {
            "peer_id": peer_id,
            "port": PORT,
            "metadata_port": metadata_port, 
            "chunk_port": chunk_server_port,
            "files": [filename]
        }

        res = requests.post(bootstrap_url, json=payload)
        print(f"[BOOTSTRAP] {res.json()}")
    except Exception as e:
        print(f"[!] Failed to register with bootstrap server: {e}")

    # Actual file transfer
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



def start_chunk_server(port):
    host = "0.0.0.0"
    s = socket.socket()
    s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    s.bind((host, port))
    s.listen(5)
    print(f"[+] Chunk server listening on port {port}...")
    while True:
        client_socket, _ = s.accept()
        threading.Thread(target=handle_chunk_request, args=(client_socket,), daemon=True).start()


def get_metadata_from_peer(peer):
    try:
        with socket.create_connection((peer['ip'], peer['metadata_port']), timeout=5) as s:
            s.settimeout(5)  # Add timeout here too
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
        print(f"[*] Downloading chunk {chunk['index']} from {peer['ip']}:{peer['chunk_port']}")

        with socket.create_connection((peer['ip'], peer['chunk_port']), timeout=5) as s:
            s.settimeout(5)  # Set per-operation timeout
            s.sendall(f"GET_CHUNK {chunk['hash']}\r\n\r\n".encode())
            
            chunk_data = bytearray()
            remaining = chunk['size']
            while remaining > 0:
                data = s.recv(min(BUFFER_SIZE, remaining))
                if not data:
                    break
                chunk_data.extend(data)
                remaining -= len(data)
                
            if remaining > 0:
                return False
                
            if compute_chunk_hash(chunk_data) != chunk['hash']:
                return False

            # Save chunk
            os.makedirs(RECEIVED_CHUNKS, exist_ok=True)
            with open(os.path.join(RECEIVED_CHUNKS, f"{chunk['hash']}.chunk"), "wb") as f:
                f.write(chunk_data)
                
            return True
    except Exception as e:
        print(f"[-] Error downloading chunk: {e}")
    return False



def reconstruct_file(metadata):
    print("[*] Reconstructing file...")
    file_path = os.path.join(RECEIVED_DIR, metadata['file_name'])
    
    with open(file_path, "wb") as f:
        # Create virtual chunk sequence
        virtual_chunks = [None] * metadata['total_chunks']
        
        # First pass: Map all chunks to their source
        for chunk in metadata['chunks']:
            source_idx = chunk['source_index']
            virtual_chunks[chunk['index']] = source_idx
        
        # Second pass: Write in order using source chunks
        for idx in range(metadata['total_chunks']):
            source_idx = virtual_chunks[idx]
            source_chunk = metadata['chunks'][source_idx]
            chunk_path = os.path.join(RECEIVED_CHUNKS, f"{source_chunk['hash']}.chunk")
            
            if os.path.exists(chunk_path):
                with open(chunk_path, "rb") as cf:
                    f.write(cf.read())
            else:
                print(f"[-] Missing source chunk {source_idx} for position {idx}")
    
    # Final validation
    if get_checksum(file_path) == metadata['file_hash']:
        print("[+] File reconstructed successfully.")
    else:
        print("[-] Hash mismatch! File corrupted.")


def download_from_multiple_peers(metadata, peers):
    # print("debug 2")
    os.makedirs(RECEIVED_CHUNKS, exist_ok=True)
    unique_chunks = {}
    for chunk in metadata['chunks']:
        unique_chunks[chunk['source_index']] = chunk
        
    chunk_queue = queue.Queue()
    for _, chunk in unique_chunks.items():
        chunk_queue.put(chunk)

    downloaded = set()
    lock = threading.Lock()
    # print("debug 3")
    def worker():
        while True:
            try:
                chunk = chunk_queue.get_nowait()
                # if os.path.exists(os.path.join(RECEIVED_CHUNKS, f"{chunk['hash']}.chunk")):
                #     chunk_queue.task_done()
                #     continue
            except queue.Empty:
                break
                
            try:
                # Check if already downloaded
                # with lock:
                #     if chunk['hash'] in downloaded:
                #         continue  # Skip if already downloaded

                # Attempt download
                for peer in peers:
                    if download_chunk(peer, chunk):
                        with lock:
                            downloaded.add(chunk['hash'])
                        break  # Break after successful download
            finally:
                # Always mark task as done
                chunk_queue.task_done()
    # print("debug 4")
    threads = [threading.Thread(target=worker) for _ in range(min(4, len(peers) * 2))]
    for t in threads:
        t.start()
    # print("debug 5")
    chunk_queue.join()
    # print("debug 6")
    for t in threads:
        t.join()
    # print("debug 7")
    if len(downloaded) == len(unique_chunks):
        reconstruct_file(metadata)
    else:
        print(f"[-] Missing {len(metadata['chunks']) - len(downloaded)} chunks.")


def receive_file(use_multiple, selected_peer_indexes):
    # Step 1: Fetch all registered peers from bootstrap server
    peers = get_available_peers()
    if not peers:
        print("No peers available to download from.")
        return

    peer_ids = list(peers.keys())

    if use_multiple:
        print("Available peers:")
        for idx, (peer_id, info) in enumerate(peers.items()):
            print(f"{idx}: {peer_id} @ {info['ip']}:{info['port']} - Files: {', '.join(info['files'])}")

        selected_peers = []
        for idx_str in selected_peer_indexes:
            try:
                idx = int(idx_str.strip())
                if idx < 0 or idx >= len(peer_ids):
                    print(f"Index {idx} out of range. Skipping.")
                    continue
                peer_info = peers[peer_ids[idx]]
                selected_peers.append({
                    "ip": peer_info['ip'],
                    "chunk_port": peer_info['chunk_port'],
                    "metadata_port": peer_info['metadata_port']
                })
            except ValueError:
                print(f"Invalid index: {idx_str}. Skipping.")

        if not selected_peers:
            print("No valid peers selected.")
            return

        metadata = get_metadata_from_peer({
            "ip": selected_peers[0]["ip"],
            "chunk_port": selected_peers[0]["chunk_port"],
            "metadata_port":selected_peers[0]["metadata_port"]
        })
        if not metadata:
            print("Failed to fetch metadata from selected peer.")
            return

        peers_list = [{
            "ip": peer_info['ip'],
            "chunk_port": peer_info['chunk_port']
        } for peer_info in selected_peers]

        download_from_multiple_peers(metadata, peers_list)

    else:
        try:
            idx = int(selected_peer_indexes[0].strip())
            if idx < 0 or idx >= len(peer_ids):
                print("Selected peer index out of range.")
                return
            selected_peer = peers[peer_ids[idx]]
            peer_info = {
                "ip": selected_peer['ip'],
                "chunk_port": selected_peer['chunk_port']
            }
        except (IndexError, ValueError):
            print("Invalid index for single peer.")
            return

        metadata = get_metadata_from_peer(peer_info)
        if not metadata:
            print("Failed to fetch metadata from peer.")
            return

        download_from_multiple_peers(metadata, [peer_info])




def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--send', help="Send a file")
    parser.add_argument('--receive', nargs=2, metavar=('USE_MULTIPLE', 'PEERS'),help="Receive a file. Example: --receive true 0,1,2")
    parser.add_argument('--server', action='store_true', help="Run chunk server")
    args = parser.parse_args()

    if args.send:
        send_file(args.send)
    elif args.receive:
        use_multiple = args.receive[0].lower() == 'true'
        selected_ids = args.receive[1].split(',') if args.receive[1] else []
        receive_file(use_multiple, selected_ids)
    elif args.server:
        # Start standalone chunk server on dynamic port
        port = get_free_port()
        print(f"[*] Starting standalone chunk server on port {port}")
        start_chunk_server(port)
    else:
        print("Usage:\n  --send <filename>\n  --receive\n  --server")

if __name__ == "__main__":
    main()
