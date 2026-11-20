"""Minimal Workbench NET API client (built-in core handlers only)."""
import json, socket, struct, sys

def _ps(s):
    b = s.encode('utf-8'); return struct.pack('<i', len(b)) + b

def call(func, params=None, host='127.0.0.1', port=5775, timeout=600):
    payload = dict(params or {}); payload['APIFunc'] = func
    req = struct.pack('<i', 1) + _ps('ClaudeUG2') + _ps('JsonRPC') + _ps(json.dumps(payload))
    s = socket.create_connection((host, port), timeout=timeout)
    s.sendall(req); s.shutdown(socket.SHUT_WR)
    buf = b''
    while True:
        c = s.recv(65536)
        if not c: break
        buf += c
    s.close()
    if not buf: return {}
    n = struct.unpack_from('<i', buf, 0)[0]; status = buf[4:4+n].decode('utf-8', 'replace')
    if status != 'Ok': raise RuntimeError('Workbench error: ' + status)
    rest = buf[4+n:]
    if len(rest) >= 4:
        m = struct.unpack_from('<i', rest, 0)[0]; p = rest[4:4+m].decode('utf-8', 'replace')
        return json.loads(p) if p else {}
    return {}

if __name__ == '__main__':
    print(json.dumps(call(sys.argv[1], json.loads(sys.argv[2]) if len(sys.argv) > 2 else {}), indent=1))
