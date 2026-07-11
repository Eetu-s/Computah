"""Minimal DLNA / UPnP AVTransport client.

Enough of the protocol to push a single image URL onto a Media Renderer:
discover the renderer over SSDP, read its device description to find the
AVTransport control URL, then POST SetAVTransportURI + Play as SOAP.

Hisense VIDAA TVs expose a UPnP AV MediaRenderer while powered on, which is
the most reliable way to display an arbitrary image without a native app.
"""
import logging
import socket
import xml.etree.ElementTree as ET
from urllib.parse import urljoin, urlparse
from xml.sax.saxutils import escape

import requests

log = logging.getLogger("computah.dlna")

SSDP_ADDR = ("239.255.255.250", 1900)
AVTRANSPORT = "urn:schemas-upnp-org:service:AVTransport:1"
_DEVICE_NS = "urn:schemas-upnp-org:device-1-0"


def discover(timeout=3, target_ip=None, st=AVTRANSPORT):
    """M-SEARCH the LAN and return description URLs (LOCATION headers)."""
    msg = "\r\n".join(
        [
            "M-SEARCH * HTTP/1.1",
            f"HOST: {SSDP_ADDR[0]}:{SSDP_ADDR[1]}",
            'MAN: "ssdp:discover"',
            f"MX: {int(timeout)}",
            f"ST: {st}",
            "",
            "",
        ]
    ).encode()

    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM, socket.IPPROTO_UDP)
    s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    s.setsockopt(socket.IPPROTO_IP, socket.IP_MULTICAST_TTL, 2)
    s.settimeout(timeout)

    locations = []
    try:
        s.sendto(msg, SSDP_ADDR)
        while True:
            try:
                data, _ = s.recvfrom(65507)
            except socket.timeout:
                break
            headers = _parse_headers(data.decode(errors="ignore"))
            loc = headers.get("location")
            if not loc:
                continue
            if target_ip and urlparse(loc).hostname != target_ip:
                continue
            if loc not in locations:
                locations.append(loc)
    finally:
        s.close()
    return locations


def _parse_headers(text):
    headers = {}
    for line in text.splitlines()[1:]:
        if ":" in line:
            key, _, value = line.partition(":")
            headers[key.strip().lower()] = value.strip()
    return headers


def control_url_from_description(location):
    """Read a UPnP device description and return the AVTransport control URL."""
    resp = requests.get(location, timeout=5)
    resp.raise_for_status()
    root = ET.fromstring(resp.content)
    for svc in root.iter(f"{{{_DEVICE_NS}}}service"):
        stype = svc.findtext(f"{{{_DEVICE_NS}}}serviceType") or ""
        if stype.startswith("urn:schemas-upnp-org:service:AVTransport"):
            ctrl = svc.findtext(f"{{{_DEVICE_NS}}}controlURL")
            if ctrl:
                return urljoin(location, ctrl), stype
    return None, None


def resolve_control_url(target_ip=None, timeout=3):
    for loc in discover(timeout=timeout, target_ip=target_ip):
        try:
            ctrl, stype = control_url_from_description(loc)
            if ctrl:
                log.info("Found AVTransport renderer at %s", ctrl)
                return ctrl, stype
        except Exception as exc:  # noqa: BLE001 - try the next candidate
            log.warning("Could not read description %s: %s", loc, exc)
    return None, None


def _didl(url, title, mime):
    return (
        '<DIDL-Lite xmlns="urn:schemas-upnp-org:metadata-1-0/DIDL-Lite/" '
        'xmlns:dc="http://purl.org/dc/elements/1.1/" '
        'xmlns:upnp="urn:schemas-upnp-org:metadata-1-0/upnp/">'
        '<item id="0" parentID="-1" restricted="1">'
        f"<dc:title>{escape(title)}</dc:title>"
        "<upnp:class>object.item.imageItem.photo</upnp:class>"
        f'<res protocolInfo="http-get:*:{mime}:'
        'DLNA.ORG_OP=01;DLNA.ORG_CI=0;'
        'DLNA.ORG_FLAGS=00d00000000000000000000000000000">'
        f"{escape(url)}</res>"
        "</item></DIDL-Lite>"
    )


def _soap(control_url, service_type, action, args):
    body_args = "".join(f"<{k}>{v}</{k}>" for k, v in args.items())
    envelope = (
        '<?xml version="1.0" encoding="utf-8"?>'
        '<s:Envelope xmlns:s="http://schemas.xmlsoap.org/soap/envelope/" '
        's:encodingStyle="http://schemas.xmlsoap.org/soap/encoding/">'
        f'<s:Body><u:{action} xmlns:u="{service_type}">'
        f"{body_args}"
        f"</u:{action}></s:Body></s:Envelope>"
    )
    headers = {
        "Content-Type": 'text/xml; charset="utf-8"',
        "SOAPAction": f'"{service_type}#{action}"',
    }
    resp = requests.post(
        control_url, data=envelope.encode(), headers=headers, timeout=8
    )
    resp.raise_for_status()
    return resp.text


def cast_image(
    image_url,
    control_url=None,
    service_type=AVTRANSPORT,
    target_ip=None,
    title="computah-cast",
    mime="image/jpeg",
    discovery_timeout=3,
):
    """Display ``image_url`` on the DLNA renderer. Returns the control URL used."""
    if not control_url:
        control_url, service_type = resolve_control_url(
            target_ip=target_ip, timeout=discovery_timeout
        )
    if not control_url:
        raise RuntimeError("No DLNA AVTransport renderer found on the network")

    metadata = _didl(image_url, title, mime)

    # Some renderers need to be stopped before a new URI is accepted.
    try:
        _soap(control_url, service_type, "Stop", {"InstanceID": "0"})
    except Exception:  # noqa: BLE001 - best effort
        pass

    _soap(
        control_url,
        service_type,
        "SetAVTransportURI",
        {
            "InstanceID": "0",
            "CurrentURI": escape(image_url),
            "CurrentURIMetaData": escape(metadata),
        },
    )
    _soap(control_url, service_type, "Play", {"InstanceID": "0", "Speed": "1"})
    return control_url
