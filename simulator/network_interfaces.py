"""Cross-platform discovery of usable local IPv4 interfaces for POS setup."""
from __future__ import annotations
import socket
import psutil

def get_network_interfaces() -> list[dict[str, object]]:
    recommended_ip = ""
    probe = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        probe.connect(("1.1.1.1", 53))
        recommended_ip = probe.getsockname()[0]
    except OSError:
        pass
    finally:
        probe.close()
    result = []
    stats = psutil.net_if_stats()
    for name, addresses in psutil.net_if_addrs().items():
        if not stats.get(name) or not stats[name].isup:
            continue
        for address in addresses:
            if address.family != socket.AF_INET:
                continue
            ip = address.address
            if ip.startswith(("127.", "169.254.")):
                continue
            result.append({"name": name, "ipv4": ip, "recommended": ip == recommended_ip})
    result.sort(key=lambda item: (not item["recommended"], item["name"].lower(), item["ipv4"]))
    return result
