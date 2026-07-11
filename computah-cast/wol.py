import socket


def wake(mac, broadcast="255.255.255.255", port=9):
    """Send a Wake-on-LAN magic packet to ``mac``.

    Hisense TVs are powered on from a full-off state via WOL to their (wired
    or wireless) MAC address. Requires host networking so the broadcast
    actually reaches the LAN.
    """
    clean = mac.replace(":", "").replace("-", "").replace(".", "").strip()
    if len(clean) != 12:
        raise ValueError(f"Invalid MAC address: {mac!r}")
    packet = bytes.fromhex("ff" * 6 + clean * 16)

    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    s.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
    try:
        s.sendto(packet, (broadcast, port))
    finally:
        s.close()
