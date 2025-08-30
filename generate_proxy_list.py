import os
import re
import json
import socket
import requests

API_URL = os.getenv(
    "PFO_API_URL",
    "https://proxyfreeonly.com/api/free-proxy-list?limit=500&page=1&country=CN&sortBy=lastChecked&sortType=desc"
)
MAX_NODES = int(os.getenv("MAX_NODES", "60"))
TEST_CONNECTIVITY = os.getenv("TEST_CONNECTIVITY", "true").lower() == "true"
CONNECT_TIMEOUT = float(os.getenv("CONNECT_TIMEOUT", "1.5"))
OUTPUT_FILENAME = os.getenv("MODULE_FILENAME", "Surge-Proxies.conf")
CANDIDATE_LIMIT = int(os.getenv("CANDIDATE_LIMIT", "200"))

IP_RE = re.compile(r"^(?:(?:\d{1,3}\.){3}\d{1,3})$")
HOST_RE = re.compile(r"^[^\s:@]+$")

LINE_PATTERNS = [
    re.compile(r"^(?:(?P<user>[^:@\s]+):(?P<pass>[^:@\s]+)@)?(?P<host>[^:\s]+):(?P<port>\d+)$"),
    re.compile(r"^(?P<host>[^:\s]+):(?P<port>\d+):(?P<user>[^:\s]+):(?P<pass>[^:\s]+)$"),
    re.compile(r"^(?P<host>[^:\s]+):(?P<port>\d+)$"),
]

def fetch_raw(url):
    r = requests.get(url, timeout=20)
    r.raise_for_status()
    return r

def try_parse_json(text):
    try:
        data = json.loads(text)
        if isinstance(data, dict):
            for key in ("data", "list", "result", "items", "proxies"):
                if isinstance(data.get(key), list):
                    return data[key]
            for v in data.values():
                if isinstance(v, list):
                    return v
            return []
        elif isinstance(data, list):
            return data
    except:
        pass
    return None

def normalize_proto(p):
    if not p:
        return None
    p = str(p).lower()
    if p.startswith("socks5") or p == "socks":
        return "socks5"
    if p in ("https",):
        return "https"
    # 过滤掉 http 和 socks4
    return None

def parse_json_records(records):
    items = []
    for rec in records:
        host = rec.get("ip") or rec.get("host") or rec.get("address") or rec.get("server") or rec.get("addr")
        port = rec.get("port")
        proto = (
            normalize_proto(rec.get("type")) or
            normalize_proto(rec.get("protocol")) or
            normalize_proto(rec.get("scheme")) or
            normalize_proto(rec.get("proxy_type"))
        )
        user = rec.get("username") or rec.get("user")
        pwd = rec.get("password") or rec.get("pass")
        if not host or not port:
            continue
        if not (IP_RE.match(host) or HOST_RE.match(host)):
            continue
        try:
            port = int(str(port))
        except:
            continue
        if not proto:
            continue
        items.append({"host": host, "port": port, "proto": proto, "user": user, "pwd": pwd})
    return items

def parse_txt_lines(text):
    items = []
    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        m = None
        for pat in LINE_PATTERNS:
            m = pat.match(line)
            if m:
                break
        if not m:
            continue
        host = m.group("host")
        port = int(m.group("port"))
        user = m.groupdict().get("user")
        pwd = m.groupdict().get("pass")
        proto = "socks5" if "socks5" in line.lower() else ("https" if "https" in line.lower() else None)
        if not proto:
            continue
        items.append({"host": host, "port": port, "proto": proto, "user": user, "pwd": pwd})
    return items

def test_connectivity(host, port, timeout):
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except:
        return False

def generate_conf(proxies):
    lines = ["[Proxy]"]
    for idx, p in enumerate(proxies, 1):
        name = f"CN-{p['proto'].upper()}-{idx}"
        base = f"{name} = {p['proto']}, {p['host']}, {p['port']}"
        if p.get("user") and p.get("pwd"):
            base += f", username={p['user']}, password={p['pwd']}"
        lines.append(base)
    lines.append("FINAL,Proxy")
    return "\n".join(lines) + "\n"

def main():
    resp = fetch_raw(API_URL)
    text = resp.text.strip()
    records = try_parse_json(text)
    if records is not None:
        proxies = parse_json_records(records)
    else:
        proxies = parse_txt_lines(text)

    uniq = {}
    for p in proxies:
        key = (p["host"], p["port"], p["proto"])
        if key not in uniq:
            uniq[key] = p
    proxies = list(uniq.values())

    if CANDIDATE_LIMIT > 0:
        proxies = proxies[:CANDIDATE_LIMIT]

    if TEST_CONNECTIVITY:
        proxies = [p for p in proxies if test_connectivity(p["host"], p["port"], CONNECT_TIMEOUT)]

    proxies = proxies[:MAX_NODES]
    conf = generate_conf(proxies)
    with open(OUTPUT_FILENAME, "w", encoding="utf-8") as f:
        f.write(conf)
    print(f"✅ {OUTPUT_FILENAME} 已生成，节点数: {len(proxies)}")

if __name__ == "__main__":
    main()
