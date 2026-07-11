import socket


def get_local_ip(target="8.8.8.8"):
    """Return the LAN IP of the interface used to reach ``target``.

    Passing the TV's IP as the target ensures we advertise an address on the
    same subnet as the TV, even on a multi-homed Raspberry Pi.
    """
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect((target, 80))
        return s.getsockname()[0]
    except OSError:
        return "127.0.0.1"
    finally:
        s.close()
