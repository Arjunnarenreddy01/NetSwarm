from flask import Flask, request, jsonify
from flask_cors import CORS  # Add this import

app = Flask(__name__)
CORS(app)  # Enable CORS for all routes

# In-memory storage of peers
registered_peers = {}

@app.route('/register', methods=['POST'])
def register_peer():
    data = request.get_json()
    peer_id = data.get("peer_id")
    port = data.get("port")
    files = data.get("files", [])
    chunk_port = data.get("chunk_port") # Get chunk_port
    metadata_port = data.get("metadata_port")

    if not peer_id or not port or not chunk_port:
        return jsonify({"status": "error", "message": "peer_id, port, and chunk_port required"}), 400

    ip = request.remote_addr
    registered_peers[peer_id] = {
        "ip": ip,
        "port": port,
        "chunk_port": chunk_port,  # Store chunk port
        "metadata_port":metadata_port,
        "files": files
    }

    print(f"[REGISTERED] {peer_id} at {ip}:{port} (chunk: {chunk_port}) — {files}")
    return jsonify({"status": "success", "peer_id": peer_id})

@app.route('/peers', methods=['GET'])
def get_peers():
    return jsonify(registered_peers)

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=8000)