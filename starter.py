import subprocess
import time

processes = []

try:
    # Start bootstrap_server.py
    processes.append(subprocess.Popen(["python", "network/bootstrap_server.py"]))

    # Start controller.py
    processes.append(subprocess.Popen(["python", "controller/controller.py"]))

    # Start npm run dev in ui-myapp
    processes.append(subprocess.Popen(
        ["npm", "run", "dev"],
        cwd="ui-myapp",     # run from ui-myapp dir
        shell=True          # required for npm commands on Windows
    ))

    print("All scripts started silently in background. Press Ctrl+C to terminate.")
    while True:
        time.sleep(1)

except KeyboardInterrupt:
    print("Terminating all processes...")
    for p in processes:
        p.terminate()
