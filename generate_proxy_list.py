import os
import re
import json
import socket
import requests

API_URL = os.getenv("PFO_API_URL", "https://proxyfreeonly.com/api/free-proxy-list?limit=500&page=1&country=CN&sortBy=lastChecked&sortType=desc")
MAX_NODES = int(os.getenv("MAX_NODES", "60"))
TEST_CONNECTIVITY = os.getenv("TEST_CONNECTIVITY", "true").lower() == "true"
CONNECT_TIMEOUT = float(os.getenv("CONNECT_TIMEOUT", "1.5"))
OUTPUT_FILENAME = "Surge-Proxies.conf"

IP_RE = re.compile(r"^(?P<ip>(?:\d{1,3}\.){3}\d{1,3})$")
HOST_RE = re.compile(r"^(?P<host>[^:\s@]+)$")
LINE_PATTERNS = [
    re.compile(r"^(?:(?P<user>[^:@\s]+):(?P<pass>[^:@\s]+)@)?(?P<host>[^:\s]+):(?P<port>\d+)$"),
    re.compile(r"^(?P<host>[^:\s]+):(?P<port>\d+):(?P<user>[^:\s]+):(?P<pass>[^:\s]+)$"),
    re.compile(r"^(?P<host>[^:\s]+):(?P<port>\d+)$"),
]

def fetch_raw(url):
    r = requests.get(url, timeout=15)
    r.raise_for_status()
    return r

def try_parse_json(text):
    try:
        data = json.loads(text)
        if isinstance(data, dict):
            for v in data.values():
                if isinstance(v, list):
                    return v
            return []
        elif isinstance(data, list):
            return data
    except:
        pass
    return None

def parse_json_records(records):
    items = []
    for p in records:
        host = p.get("ip") or p.get("host") or p.get("address") or p.get("server") or p.get("addr")
        port = p.get("port")
        proto = (p.get("type") or p.get("protocol") or "socks5").lower()
        user = p.get("username") or p.get("user")
        pwd = p.get("password") or p.get("pass")
        if not host or not port:
            continue
        if not (IP_RE.match
