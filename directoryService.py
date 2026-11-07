import socket
import sys
import threading
import time

HOST = "127.0.0.1"
DIR_PORT = 9000 
BUFFER = 1024
REGISTRY = []
REGISTRY_LOCK = threading.Lock()

def send_line(sock, s):
    sock.sendall((s.rstrip("\n") + "\n").encode("utf-8"))

def recv_line(sock):
    data = bytearray()
    while True:
        ch = sock.recv(1)
        if not ch:
            return ""
        data += ch
        if ch == b"\n":
            return data.decode("utf-8", errors="replace").rstrip("\n")

def dir_handle(conn, addr):
    with conn:
        # command = REGISTER or LIST
        line = recv_line(conn)
        if not line:
            return
        parts = line.strip().split()
        cmd = parts[0].upper()

        if cmd == "REGISTER" and len(parts) == 4:
            name, host, port_str = parts[1], parts[2], parts[3]
            try:
                port = int(port_str)
            except ValueError:
                send_line(conn, "ERR invalid port")
                return
            with REGISTRY_LOCK:
                entry = {"name": name, "host": host, "port": port}
                REGISTRY[:] = [e for e in REGISTRY if not (e["name"] == name and e["host"] == host and e["port"] == port)]
                REGISTRY.append(entry)
            send_line(conn, "OK")
            recv_line(conn)
            with REGISTRY_LOCK:
                REGISTRY[:] = [e for e in REGISTRY if not (e["name"] == name and e["host"] == host and e["port"] == port)]
        elif cmd == "LIST":
            with REGISTRY_LOCK:
                entries = list(REGISTRY)
            for e in entries:
                send_line(conn, f'{e["name"]} {e["host"]} {e["port"]}')
            send_line(conn, "END")
        else:
            send_line(conn, "ERR unknown command")

def run_directory():
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    s.bind((HOST, DIR_PORT))
    s.listen()
    print(f"[DIR] Listening on {HOST}:{DIR_PORT}")
    try:
        while True:
            conn, addr = s.accept()
            threading.Thread(target=dir_handle, args=(conn, addr), daemon=True).start()
    except KeyboardInterrupt:
        print("\n[DIR] Shutting down")
    finally:
        s.close()

def run_server(name="srv1", host=HOST, port=9101, dir_host=HOST, dir_port=DIR_PORT):
    connected_clients = []
    clients_lock = threading.Lock()

    def broadcast(message):
        with clients_lock:
            recipients = list(connected_clients)

        for client in recipients:
            try:
                client.sendall(message.encode())
            except OSError:
                pass

    def handle_client(c, a):
        print(f"[{name}] client {a} connected")
        with clients_lock:
            connected_clients.append(c)

        try:
            with c:
                while True:
                    data = c.recv(BUFFER)
                    if not data:
                        break
                    msg = data.decode(errors="replace")
                    broadcast(f"[{name}] {msg}")
        finally:
            with clients_lock:
                connected_clients.remove(c)
            print(f"[{name}] client {a} disconnected")

    listener = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    listener.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    listener.bind((host, port))
    listener.listen()
    print(f"[{name}] Serving on {host}:{port}")

    reg_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        reg_sock.connect((dir_host, dir_port))
        send_line(reg_sock, f"REGISTER {name} {host} {port}")
        resp = recv_line(reg_sock)
        if resp != "OK":
            print(f"[{name}] Directory registration failed: {resp}")
            reg_sock.close()
            reg_sock = None
        else:
            print(f"[{name}] Registered with directory {dir_host}:{dir_port}")
    except Exception as e:
        print(f"[{name}] Could not register with directory: {e}")
        reg_sock = None
    try:
        while True:
            conn, addr = listener.accept()
            threading.Thread(target=handle_client, args=(conn, addr), daemon=True).start()
    except KeyboardInterrupt:
        print(f"\n[{name}] Shutting down")
    finally:
        listener.close()
        if reg_sock:
            try:
                reg_sock.close()
            except:
                pass


def run_client(dir_host=HOST, dir_port=DIR_PORT):
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.connect((dir_host, dir_port))
        send_line(s, "LIST")
        servers = []
        while True:
            line = recv_line(s)
            if not line:
                print("[CLIENT] Directory closed")
                return
            if line == "END":
                break
            parts = line.split()
            if len(parts) == 3:
                name, host, port_str = parts
                try:
                    servers.append((name, host, int(port_str)))
                except:
                    pass
    if not servers:
        print("[CLIENT] No servers available")
        return
    print("[CLIENT] Available servers:")
    for i, (name, host, port) in enumerate(servers, 1):
        print(f"  {i}) {name} @ {host}:{port}")
    choice = input("Pick a server number: ").strip()
    try:
        idx = int(choice) - 1
        name, host, port = servers[idx]
    except Exception:
        print("[CLIENT] Invalid choice")
        return
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.connect((host, port))
        print(f"[CLIENT] Connected to {name} @ {host}:{port}")
        while True:
            msg = input("Say something ('exit' to quit): ")
            if msg.strip().lower() == "exit":
                print("[CLIENT] Bye!")
                break
            s.sendall(msg.encode())
            data = s.recv(BUFFER)
            if not data:
                print("[CLIENT] Server closed connection")
                break
            print(data.decode().rstrip())

if len(sys.argv) < 2:
    print("Usage:")
    print("  python3 directoryService.py directory")
    print("  python3 directoryService.py server <name> <port>")
    print("  python3 directoryService.py client")
    sys.exit(1)

role = sys.argv[1]
if role == "directory":
    run_directory()
elif role == "server":
    if len(sys.argv) != 4:
        print("Usage: python3 directoryService.py server <name> <port>")
        sys.exit(1)
    name = sys.argv[2]
    port = int(sys.argv[3])
    run_server(name=name, port=port)
elif role == "client":
    run_client()
else:
    print("Unknown role")
    sys.exit(1)
