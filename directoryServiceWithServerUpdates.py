import socket
import sys
import threading
import time
import random

HOST = "127.0.0.1"
DIR_PORT = 9000
BUFFER = 1024
REGISTRY = []
REG_LOCK = threading.Lock()

def generate_random_number(rmin, rmax):
    """Return one random integer from rmin to rmax, inclusive."""
    return random.randint(rmin, rmax)

def send_line(sock, s):
    try:
        sock.sendall((s.rstrip("\n") + "\n").encode("utf-8"))
    except Exception:
        pass

def recv_line(sock):
    data = bytearray()
    try:
        while True:
            ch = sock.recv(1)
            if not ch:
                return ""
            data += ch
            if ch == b"\n":
                return data.decode("utf-8", errors="replace").rstrip("\n")
    except Exception:
        return ""


def dir_handle(conn, addr):
    with conn:
        line = recv_line(conn)
        if not line:
            return
        parts = line.split()
        cmd = parts[0].upper()

        if cmd == "REGISTER" and len(parts) == 4:
            name, host, port_s = parts[1], parts[2], parts[3]
            try:
                port = int(port_s)
            except ValueError:
                send_line(conn, "ERR invalid port")
                return
            with REG_LOCK:
                REGISTRY[:] = [e for e in REGISTRY if not (e["name"] == name and e["host"] == host and e["port"] == port)]
                REGISTRY.append({"name": name, "host": host, "port": port})
            send_line(conn, "OK")
            recv_line(conn)
            with REG_LOCK:
                REGISTRY[:] = [e for e in REGISTRY if not (e["name"] == name and e["host"] == host and e["port"] == port)]
        elif cmd == "LIST":
            with REG_LOCK:
                entries = list(REGISTRY)
            for e in entries:
                send_line(conn, f'{e["name"]} {e["host"]} {e["port"]}')
            send_line(conn, "END")
        else:
            send_line(conn, "ERR unknown")

def run_directory():
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    s.bind((HOST, DIR_PORT))
    s.listen()
    print(f"[DIR] Listening on {HOST}:{DIR_PORT}")
    try:
        while True:
            c, a = s.accept()
            threading.Thread(target=dir_handle, args=(c, a), daemon=True).start()
    except KeyboardInterrupt:
        print("\n[DIR] Bye")
    finally:
        s.close()

class PeerSet:
    def __init__(self):
        self._lock = threading.Lock()
        self._peers = {}  # name -> socket

    def names(self):
        with self._lock:
            return list(self._peers.keys())

    def add(self, name, sock):
        with self._lock:
            old = self._peers.get(name)
            self._peers[name] = sock
            if old and old is not sock:
                try: old.close()
                except: pass

    def get_sockets(self):
        with self._lock:
            return list(self._peers.items())

    def remove(self, name):
        with self._lock:
            s = self._peers.pop(name, None)
        if s:
            try: s.close()
            except: pass

    def broadcast(self, line):
        for _, s in self.get_sockets():
            send_line(s, line)

def run_server(name="srv1", host=HOST, port=9101, dir_host=HOST, dir_port=DIR_PORT):
    peers = PeerSet()
    numbers = []
    numbers_lock = threading.Lock()

    def collect_number(number, source):
        with numbers_lock:
            numbers.append(number)
            count = len(numbers)
            average = sum(numbers) / count
        print(f"[{name}] collected {number} from {source} (count: {count})")
        print(f"[{name}] current average: {average:.2f}")

    def accept_loop(listener):
        while True:
            c, a = listener.accept()
            threading.Thread(target=classify_and_handle, args=(c, a), daemon=True).start()

    def classify_and_handle(conn, addr):
        first = recv_line(conn)
        if not first:
            try: conn.close()
            except: pass
            return
        parts = first.split()
        if len(parts) == 2 and parts[0].upper() == "PEER":
            pname = parts[1]
            peers.add(pname, conn)
            peer_reader(pname, conn)  
        elif first.strip().upper() == "CLIENT":
            handle_client(conn, addr)
        else:
            handle_client(conn, addr, first_line=first)

    def handle_client(c, a, first_line=None):
        print(f"[{name}] client {a} connected")
        try:
            send_line(c, f"Welcome to {name}. Type 'exit' to quit.")
            if first_line is not None:
                if first_line.strip().lower() == "exit":
                    return
                process_local_msg(first_line, c)

            while True:
                line = recv_line(c)
                if not line or line.strip().lower() == "exit":
                    break
                process_local_msg(line, c)
        finally:
            print(f"[{name}] client {a} disconnected")
            try: c.close()
            except: pass

    def process_local_msg(text, client_sock):
        try:
            number = int(text)
        except ValueError:
            send_line(client_sock, f"[{name}] Please send an integer")
            return

        collect_number(number, "client")
        send_line(client_sock, f"[you@{name}] {number}")
        peers.broadcast(f"MSG {name} {number}")

    def peer_reader(peer_name, sock):
        print(f"[{name}] peer connected: {peer_name}")
        try:
            while True:
                line = recv_line(sock)
                if not line:
                    break
                parts = line.split(" ", 2)
                if len(parts) == 3 and parts[0] == "MSG":
                    origin, payload = parts[1], parts[2]
                    try:
                        number = int(payload)
                    except ValueError:
                        continue
                    collect_number(number, f"peer {origin}")
                # ignore unknown
        finally:
            print(f"[{name}] peer disconnected: {peer_name}")
            peers.remove(peer_name)

    def connect_to_peer(phost, pport, pname):
        # Each server pair needs only one connection. The alphabetically earlier
        # server opens it; the other server simply accepts it.
        if pname <= name or pname in peers.names():
            return
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            s.connect((phost, pport))
            send_line(s, f"PEER {name}")
            peers.add(pname, s)
            threading.Thread(target=peer_reader, args=(pname, s), daemon=True).start()
        except Exception:
            pass

    def peer_connector():
        while True:
            try:
                with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                    s.connect((dir_host, dir_port))
                    send_line(s, "LIST")
                    entries = []
                    while True:
                        line = recv_line(s)
                        if not line or line == "END":
                            break
                        p = line.split()
                        if len(p) == 3:
                            nm, h, pt = p[0], p[1], int(p[2])
                            entries.append((nm, h, pt))
                for nm, h, pt in entries:
                    connect_to_peer(h, pt, nm)
            except Exception:
                pass
            time.sleep(1.5)

    listener = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    listener.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    listener.bind((host, port))
    listener.listen()
    print(f"[{name}] Serving on {host}:{port}")
    reg_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        reg_sock.connect((dir_host, dir_port))
        send_line(reg_sock, f"REGISTER {name} {host} {port}")
        if recv_line(reg_sock) != "OK":
            print(f"[{name}] Directory registration failed")
            reg_sock.close()
            reg_sock = None
        else:
            print(f"[{name}] Registered with directory")
    except Exception as e:
        print(f"[{name}] Could not register with directory: {e}")
        reg_sock = None

    threading.Thread(target=peer_connector, daemon=True).start()
    threading.Thread(target=accept_loop, args=(listener,), daemon=True).start()
    try:
        while True:
            time.sleep(3600)
    except KeyboardInterrupt:
        print(f"\n[{name}] Bye")
    finally:
        try: listener.close()
        except: pass
        if reg_sock:
            try: reg_sock.close()
            except: pass
        for nm in peers.names():
            peers.remove(nm)

def run_client(dir_host=HOST, dir_port=DIR_PORT, rmin=1, rmax=100, interval=60):
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
            p = line.split()
            if len(p) == 3:
                servers.append((p[0], p[1], int(p[2])))
    if not servers:
        print("[CLIENT] No servers available")
        return

    print("[CLIENT] Available servers:")
    for i, (nm, h, pt) in enumerate(servers, 1):
        print(f"  {i}) {nm} @ {h}:{pt}")

    try:
        idx = int(input("Pick a server number: ").strip()) - 1
        name, host, port = servers[idx]
    except Exception:
        print("[CLIENT] Invalid choice")
        return
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.connect((host, port))
        print(f"[CLIENT] Connected to {name} @ {host}:{port}")
        send_line(s, "CLIENT")
        welcome = recv_line(s)
        if not welcome:
            print("[CLIENT] Server closed connection")
            return
        print(welcome)

        try:
            while True:
                number = generate_random_number(rmin, rmax)
                print(f"[CLIENT] Generated number: {number}")
                send_line(s, str(number))

                response = recv_line(s)
                if not response:
                    print("[CLIENT] Server closed connection")
                    break
                print(response)
                time.sleep(interval)
        except KeyboardInterrupt:
            print("\n[CLIENT] Bye")

if len(sys.argv) < 2:
    print("Usage:\n  python3 directoryServiceWithServerUpdates.py directory\n  python3 directoryServiceWithServerUpdates.py server <name> <port>\n  python3 directoryServiceWithServerUpdates.py client")
    sys.exit(1)

role = sys.argv[1]
if role == "directory":
    run_directory()
elif role == "server":
    if len(sys.argv) != 4:
        print("Usage: python3 directoryServiceWithServerUpdates.py server <name> <port>")
        sys.exit(1)
    run_server(name=sys.argv[2], port=int(sys.argv[3]))
elif role == "client":
    run_client()
else:
    print("Unknown role")
    sys.exit(1)
