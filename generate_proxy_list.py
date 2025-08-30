import os
import re
import json
import socket
import requests

API_URL = os.getenv(
    "PFO_API_URL",
    "https://proxyfreeonly.com/api/free-proxy-list?limit=500&page=1&country=CN&sortBy=lastChecked&sortType=desc"
)
MAX_NODES = int(os.getenv("MAX_NODES", "0"))  # 0 表示不限制
TEST_CONNECTIVITY = os.getenv("TEST_CONNECTIVITY", "true").lower() == "true"
CONNECT_TIMEOUT = float(os.getenv("CONNECT_TIMEOUT", "1.5"))
OUTPUT_FILENAME = os.getenv("MODULE_FILENAME", "Surge-Proxies.conf")

IP_RE = re.compile(r"^(?:(?:\d{1,3}\.){3}\d{1,3})$")
HOST_RE = re.compile(r"^[^\s:@]+$")

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

def normalize_proto_list(protocols):
    """优先 socks5，其次 https"""
    if not protocols:
        return None
    # 优先 socks5
    for p in protocols:
        p = str(p).lower()
        if p.startswith("socks5") or p == "socks":
            return "socks5"
    # 再匹配 https
    for p in protocols:
        p = str(p).lower()
        if p == "https":
            return "https"
    return None

def parse_json_records(records):
    items = []
    for rec in records:
        host = rec.get("ip") or rec.get("host") or rec.get("address") or rec.get("server") or rec.get("addr")
        port = rec.get("port")
        proto = normalize_proto_list(rec.get("protocols")) or \
                normalize_proto_list([rec.get("type")]) or \
                normalize_proto_list([rec.get("protocol")]) or \
                normalize_proto_list([rec.get("scheme")]) or \
                normalize_proto_list([rec.get("proxy_type")])
        city = rec.get("city") or "Unknown"
        if not host or not port or not proto:
            continue
        if not (IP_RE.match(host) or HOST_RE.match(host)):
            continue
        try:
            port = int(str(port))
        except:
            continue
        items.append({"host": host, "port": port, "proto": proto, "city": city})
    return items

def test_connectivity(host, port, timeout):
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except:
        return False

def format_city(name):
    """格式化城市名：首字母大写，其余小写"""
    return name.strip().title().replace(" ", "")

def generate_conf(proxies):
    lines = ["[Proxy]"]
    # 按城市+协议分组
    grouped = {}
    for p in proxies:
        city = format_city(p["city"])
        proto = p["proto"]
        grouped.setdefault((city, proto), []).append(p)

    # 输出 socks5 节点
    for (city, proto), plist in grouped.items():
        if proto != "socks5":
            continue
        for idx, node in enumerate(plist, 1):
            lines.append(f"China {city} Socks5 {idx:02d} = socks5, {node['host']}, {node['port']}")

    # 输出 https 节点
    for (city, proto), plist in grouped.items():
        if proto != "https":
            continue
        for idx, node in enumerate(plist, 1):
            lines.append(f"China {city} HTTPS {idx:02d} = https, {node['host']}, {node['port']}")

    lines.append("")
    lines.append("[Proxy Group]")
    lines.append("Proxy = select, DIRECT, no-alert=0, hidden=0, include-all-proxies=0")
    lines.append("")
    lines.append("[Rule]")
    lines.append("FINAL,Proxy")
    return "\n".join(lines) + "\n"

def main():
    resp = fetch_raw(API_URL)
    text = resp.text.strip()
    records = try_parse_json(text)
    if records is None:
        print("❌ API 返回的不是 JSON 或无法解析")
        return

    proxies = parse_json_records(records)

    # 去重（按 IP+端口+协议+城市）
    uniq = {}
    for p in proxies:
        key = (p["host"], p["port"], p["proto"], p["city"])
        if key not in uniq:
            uniq[key] = p
    proxies = list(uniq.values())

    # 测试连通性
    if TEST_CONNECTIVITY:
        proxies = [p for p in proxies if test_connectivity(p["host"], p["port"], CONNECT_TIMEOUT)]

    # 限制最终数量
    if MAX_NODES > 0:
        proxies = proxies[:MAX_NODES]

    conf = generate_conf(proxies)
    with open(OUTPUT_FILENAME, "w", encoding="utf-8") as f:
        f.write(conf)

    print(f"✅ {OUTPUT_FILENAME} 已生成，节点数: {len(proxies)}")

if __name__ == "__main__":
    main()
