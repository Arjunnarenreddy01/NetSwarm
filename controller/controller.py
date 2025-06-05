# controller.py
from flask import Flask, request, jsonify
from flask_cors import CORS
import os
import subprocess
import threading
import uuid
import json
import requests
from flask import send_file

RECEIVED_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'received_file')

app = Flask(__name__)
CORS(app)

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


# Proxy peer requests to bootstrap server
@app.route('/peers', methods=['GET'])
def get_peers():
    try:
        bootstrap_url = "http://localhost:8000/peers"
        res = requests.get(bootstrap_url)
        return jsonify(res.json()), res.status_code
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/send', methods=['POST'])
def send_file_route():  # Renamed to avoid conflict
    if 'file' not in request.files:
        return jsonify({"error": "No file part"}), 400
        
    file = request.files['file']
    if file.filename == '':
        return jsonify({"error": "No selected file"}), 400
        
    # Generate unique filename
    unique_filename = f"temp_{uuid.uuid4().hex}_{file.filename}"
    
    # Get project root (assuming Flask app is in project_root/app)
    project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    
    # Save to peer's expected directory
    target_dir = os.path.join(project_root, 'sending_file', 'files_to_send')
    os.makedirs(target_dir, exist_ok=True)
    file_path = os.path.join(target_dir, unique_filename)
    file.save(file_path)
    
    # Start peer process in background
    def run_peer():
        peer_script = os.path.join(project_root, 'peer', 'peer.py')
        try:
            # Pass only filename (not full path) to peer script
            subprocess.Popen(
                ['python', peer_script, '--send', unique_filename],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL
            )
            # Note: File cleanup now handled by peer process
        except Exception as e:
            print(f"Error starting peer: {e}")

    threading.Thread(target=run_peer).start()
    return jsonify({"message": "File sending started"}), 202


@app.route('/receive', methods=['POST'])
def receive_file():
    data = request.json
    use_multiple = data.get('useMultiple', False)
    selected_peers = data.get('peers', [])  # These are peer *names*

    # Get peer list from bootstrap
    all_peers = get_available_peers()
    peer_ids = list(all_peers.keys())

    # Convert selected peer IDs to their corresponding indexes
    selected_indexes = []
    for pid in selected_peers:
        if pid in peer_ids:
            selected_indexes.append(str(peer_ids.index(pid)))
        else:
            print(f"Peer ID '{pid}' not found in available peer list")

    # Build the command
    cmd = [
        'python', 'peer/peer.py',
        '--receive',
        str(use_multiple),
        ','.join(selected_indexes)
    ]

    # Run in background
    threading.Thread(target=lambda: subprocess.run(cmd, check=True)).start()

    return jsonify({"message": "File download started"}), 202


@app.route('/download/<filename>', methods=['GET'])
def download_file(filename):
    file_path = os.path.join(RECEIVED_DIR, filename)
    if os.path.exists(file_path):
        return send_file(file_path, as_attachment=True)
    else:
        return jsonify({'error': 'File not found'}), 404


if __name__ == '__main__':
    app.run(port=5000, debug=True)