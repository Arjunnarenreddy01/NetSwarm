import socket
import argparse
import os
import sys
import json
from tqdm import tqdm

# Add project root to path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from utils.file_utils import (
    get_checksum, 
    chunk_file, 
    save_nmeta_file, 
    compute_chunk_hash,
    get_file_path
)

BUFFER_SIZE = 4096
SEPARATOR = "<SEPARATOR>"
CHUNK_SEPARATOR = "<CHUNK_SEP>"
PORT = 5001

def send_file(filename):
    host = "0.0.0.0"
    s = socket.socket()
    s.bind((host, PORT))
    s.listen(1)
    print(f"[+] Waiting for connection on port {PORT}...")

    client_socket, address = s.accept()
    print(f"[+] Connected to {address}")

    # Get absolute path to file
    file_path = get_file_path(filename)
    if not os.path.exists(file_path):
        print(f"[-] File not found: {file_path}")
        client_socket.close()
        s.close()
        return

    # Generate file metadata and chunks
    metadata = chunk_file(file_path)
    nmeta_path = save_nmeta_file(metadata, os.path.join("..", "sent_files"))
    print(f"[+] Generated metadata for {metadata['total_chunks']} chunks")

    # Send metadata first
    metadata_str = json.dumps(metadata)
    client_socket.send(f"{metadata_str}{SEPARATOR}".encode())

    # Send chunks one by one
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

    client_socket.close()
    s.close()
    print("[+] File chunks sent successfully.")

def receive_file():
    sender_ip = input("Enter sender IP address: ").strip()
    s = socket.socket()
    s.connect((sender_ip, PORT))
    print("[+] Connected to sender")

    # Receive metadata
    received = b""
    while SEPARATOR.encode() not in received:
        received += s.recv(BUFFER_SIZE)
    metadata_str, received = received.split(SEPARATOR.encode(), 1)
    metadata = json.loads(metadata_str.decode())
    
    # Create received_files directory in project root
    received_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "received_files")
    os.makedirs(received_dir, exist_ok=True)
    output_path = os.path.join(received_dir, metadata['file_name'])
    temp_chunks = {chunk['index']: None for chunk in metadata['chunks']}

    print(f"[+] Receiving {metadata['total_chunks']} chunks...")
    
    with open(output_path, "wb") as f, tqdm(total=metadata['file_size'], unit="B", unit_scale=True) as progress:
        while len([c for c in temp_chunks.values() if c is not None]) < metadata['total_chunks']:
            header = b""
            while SEPARATOR.encode() not in header:
                header += s.recv(BUFFER_SIZE)
            chunk_header, chunk_data = header.split(SEPARATOR.encode(), 1)
            
            index, chunk_hash, chunk_size = chunk_header.decode().split(CHUNK_SEPARATOR)
            index = int(index)
            chunk_size = int(chunk_size)
            
            remaining = chunk_size - len(chunk_data)
            while remaining > 0:
                new_data = s.recv(min(BUFFER_SIZE, remaining))
                chunk_data += new_data
                remaining -= len(new_data)
            
            if compute_chunk_hash(chunk_data) != chunk_hash:
                print(f"[-] Chunk {index} hash mismatch!")
                continue
                
            temp_chunks[index] = chunk_data
            progress.update(len(chunk_data))

        for index in sorted(temp_chunks.keys()):
            if temp_chunks[index] is not None:
                f.write(temp_chunks[index])

    s.close()

    actual_hash = get_checksum(output_path)
    if actual_hash == metadata['file_hash']:
        print("[+] File hash matched. File received successfully.")
        save_nmeta_file(metadata, received_dir)
    else:
        print("[-] File hash mismatch! File may be corrupted.")

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--send', help="Send a file (must be in sending_file/files_to_send)")
    parser.add_argument('--receive', action='store_true', help="Receive a file")
    args = parser.parse_args()

    if args.send:
        send_file(args.send)
    elif args.receive:
        receive_file()
    else:
        print("Usage:")
        print("  --send <filename>  # File must be in sending_file/files_to_send")
        print("  --receive")

if __name__ == "__main__":
    main()