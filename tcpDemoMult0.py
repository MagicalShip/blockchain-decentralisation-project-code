import socket
import sys
import threading

HOST = "127.0.0.1"
PORT = 12345
message_count = 0
counter_lock = threading.Lock()


def handle_client(conn, addr):
    global message_count
    print(f"[SERVER] Connected: {addr}")
    with conn:
        while True:
            data = conn.recv(1024)
            if not data:
                print(f"[SERVER] Disconnected: {addr}")
                break
            msg = data.decode(errors="replace")
            with counter_lock:
                message_count += 1
                current_count = message_count
            print(f"[SERVER] {addr} said: {msg}")
            conn.sendall(f"Echo #{current_count}: {msg}".encode())

def run_server():
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    s.bind((HOST, PORT))
    s.listen()
    print(f"[SERVER] Listening on {HOST}:{PORT} (Ctrl+C to stop)")
    try:
        while True:
            conn, addr = s.accept()
            threading.Thread(target=handle_client, args=(conn, addr), daemon=True).start()
    except KeyboardInterrupt:
        print("\n[SERVER] Shutting down")
    finally:
        s.close()

def run_client():
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.connect((HOST, PORT))
        print(f"[CLIENT] Connected to {HOST}:{PORT}")
        while True:
            msg = input("Say something ('exit' to quit): ")
            if msg.strip().lower() == "exit":
                print("[CLIENT] Bye!")
                break
            s.sendall(msg.encode())
            data = s.recv(1024)
            if not data:
                print("[CLIENT] Server closed connection")
                break
            print(f"[CLIENT] Received: {data.decode()}")


if len(sys.argv) != 2 or sys.argv[1] not in {"server", "client"}:
    print("Usage: python3 tcpDemoMult0.py [server|client]")
    sys.exit(1)
(run_server if sys.argv[1] == "server" else run_client)()
