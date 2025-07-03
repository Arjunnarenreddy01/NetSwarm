import os
import shutil
import subprocess
import time

def clear_folder(path, exclude_folders=None):
    """Clears contents of a folder, optionally excluding subfolders"""
    exclude_folders = exclude_folders or []

    if os.path.exists(path):
        for item in os.listdir(path):
            item_path = os.path.join(path, item)
            if item in exclude_folders:
                continue
            try:
                if os.path.isfile(item_path) or os.path.islink(item_path):
                    os.unlink(item_path)
                elif os.path.isdir(item_path):
                    shutil.rmtree(item_path)
            except Exception as e:
                print(f"Failed to delete {item_path}. Reason: {e}")

# Absolute paths
BASE = r"C:\Users\arjun\OneDrive\Documents\projects\NETSWARM\NetSwarm"

folders_to_clear = [
    os.path.join(BASE, "sending_file", "files_to_send"),
    os.path.join(BASE, "received_files"),
    os.path.join(BASE, "peer", "sent_files"),
]

# Clear folders, keeping 'chunks' in the appropriate folders
clear_folder(folders_to_clear[0])  # full clear: files_to_send
clear_folder(folders_to_clear[1], exclude_folders=["chunks"])  # keep 'chunks' in received_files
clear_folder(os.path.join(folders_to_clear[1], "chunks"))       # clear inside chunks

clear_folder(folders_to_clear[2], exclude_folders=["chunks"])  # keep 'chunks' in sent_files
clear_folder(os.path.join(folders_to_clear[2], "chunks"))       # clear inside chunks

print("✅ All specified folders cleared.")

# --- Start processes ---
processes = []

try:
    processes.append(subprocess.Popen(["python", "network/bootstrap_server.py"]))
    processes.append(subprocess.Popen(["python", "controller/controller.py"]))
    processes.append(subprocess.Popen(
        ["npm", "run", "dev"],
        cwd=os.path.join(BASE, "ui-myapp"),
        shell=True
    ))

    print("🚀 All scripts started. Press Ctrl+C to terminate.")
    while True:
        time.sleep(1)

except KeyboardInterrupt:
    print("\n🛑 Terminating all processes...")
    for p in processes:
        p.terminate()
    print("✅ All processes terminated.")
