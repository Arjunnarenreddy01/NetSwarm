import socket
import argparse
import os
import sys
from tqdm import tqdm

# Enable importing from ../util/
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
from utils.file_utils import get_checksum

BUFFER_SIZE = 4096
SEPARATOR = "<SEPARATOR>"
PORT = 5001

def send_file(filename):
    host = "0.0.0.0"
    s = socket.socket()
    s.bind((host, PORT))
    s.listen(1)
    print(f"[+] Waiting for connection on port {PORT}...")

    client_socket, address = s.accept()
    print(f"[+] Connected to {address}")

    filesize = os.path.getsize(filename)
    checksum = get_checksum(filename)
    metadata = f"{os.path.basename(filename)}{SEPARATOR}{filesize}{SEPARATOR}{checksum}"
    client_socket.send(metadata.encode())

    with open(filename, "rb") as f, tqdm(total=filesize, unit="B", unit_scale=True) as progress:
        while chunk := f.read(BUFFER_SIZE):
            client_socket.sendall(chunk)
            progress.update(len(chunk))

    client_socket.close()
    s.close()
    print("[+] File sent successfully.")

def receive_file():
    sender_ip = input("Enter sender IP address: ").strip()
    s = socket.socket()
    s.connect((sender_ip, PORT))
    print("[+] Connected to sender")

    # Receive metadata
    received = s.recv(BUFFER_SIZE).decode()
    filename, filesize, expected_checksum = received.split(SEPARATOR)
    filename = os.path.basename(filename)
    filesize = int(filesize)

    os.makedirs("received_files", exist_ok=True)
    output_path = os.path.join("received_files", f"received_{filename}")

    with open(output_path, "wb") as f, tqdm(total=filesize, unit="B", unit_scale=True) as progress:
        while filesize:
            bytes_read = s.recv(min(BUFFER_SIZE, filesize))
            if not bytes_read:
                break
            f.write(bytes_read)
            filesize -= len(bytes_read)
            progress.update(len(bytes_read))

    s.close()

    actual_checksum = get_checksum(output_path)
    if actual_checksum == expected_checksum:
        print("[+] Checksum matched. File received successfully.")
    else:
        print("[-] Checksum mismatch. File may be corrupted.")

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--send', help="Send a file")
    parser.add_argument('--receive', action='store_true', help="Receive a file")
    args = parser.parse_args()

    if args.send:
        send_file(args.send)
    elif args.receive:
        receive_file()
    else:
        print("Usage:\n  --send <filename>\n  --receive")

if __name__ == "__main__":
    main()
