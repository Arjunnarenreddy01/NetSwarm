from flask import Flask, request, jsonify

app = Flask(__name__)

# In-memory storage of peers
registered_peers = {}

@app.route('/register', methods=['POST'])
def register_peer():
    data = request.get_json()
    peer_id = data.get("peer_id")
    port = data.get("port")
    files = data.get("files", [])

    if not peer_id or not port:
        return jsonify({"status": "error", "message": "peer_id and port required"}), 400

    ip = request.remote_addr  # Get actual IP from request
    registered_peers[peer_id] = {
        "ip": ip,
        "port": port,
        "chunk_port": data["chunk_port"],
        "files": files
    }

    print(f"[REGISTERED] {peer_id} at {ip}:{port} — {files}")
    return jsonify({"status": "success", "peer_id": peer_id})

@app.route('/peers', methods=['GET'])
def get_peers():
    return jsonify(registered_peers)

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=8000)
