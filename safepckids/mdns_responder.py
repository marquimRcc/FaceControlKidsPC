"""Responder mDNS leve (stdlib puro) para anunciar um nome amigavel na rede local.

Permite acessar o controle remoto via http://controle-remoto-pckids.local:8765/remote
em dispositivos com suporte a mDNS (Windows 10/11, iOS, macOS, Android 12+, Linux)
sem depender de reserva DHCP no roteador.
"""
from __future__ import annotations

import logging
import socket
import struct
import threading
from typing import Callable, Optional

logger = logging.getLogger("safepckids.mdns")

MDNS_ADDR = "224.0.0.251"
MDNS_PORT = 5353
DEFAULT_REMOTE_HOSTNAME = "controle-remoto-pckids.local"


def _encode_dns_name(hostname: str) -> bytes:
    parts = [p for p in hostname.strip(".").split(".") if p]
    out = bytearray()
    for part in parts:
        encoded = part.encode("ascii", errors="ignore")[:63]
        out.append(len(encoded))
        out.extend(encoded)
    out.append(0)
    return bytes(out)


def _decode_dns_name(packet: bytes, offset: int) -> tuple[str, int]:
    labels: list[str] = []
    jumped = False
    original_offset = offset
    seen_offsets: set[int] = set()

    while offset < len(packet):
        if offset in seen_offsets:
            return "", original_offset + 1
        seen_offsets.add(offset)

        length = packet[offset]
        if length == 0:
            offset += 1
            break
        if (length & 0xC0) == 0xC0:
            if offset + 1 >= len(packet):
                return "", len(packet)
            pointer = ((length & 0x3F) << 8) | packet[offset + 1]
            if not jumped:
                original_offset = offset + 2
                jumped = True
            offset = pointer
            continue
        offset += 1
        if offset + length > len(packet):
            return "", len(packet)
        labels.append(packet[offset : offset + length].decode("ascii", errors="ignore"))
        offset += length

    next_offset = original_offset if jumped else offset
    return ".".join(labels).lower(), next_offset


def build_mdns_a_response(hostname: str, ip_address: str, ttl: int = 60) -> bytes:
    """Constroi um pacote de resposta mDNS (A record, AA=1)."""
    qname = _encode_dns_name(hostname)
    ip_bytes = socket.inet_aton(ip_address)
    header = struct.pack("!HHHHHH", 0, 0x8400, 0, 1, 0, 0)
    # Cache-flush bit (0x8001) para registro unico da maquina na LAN
    answer = qname + struct.pack("!HHIH", 1, 0x8001, ttl, 4) + ip_bytes
    return header + answer


def should_answer_mdns_query(packet: bytes, target_hostname: str) -> bool:
    """Retorna True se o pacote DNS for uma consulta A/ANY para target_hostname."""
    if len(packet) < 12:
        return False
    _, flags, qdcount, _, _, _ = struct.unpack("!HHHHHH", packet[:12])
    if (flags & 0x8000) != 0 or qdcount == 0 or qdcount > 32:
        return False

    target = target_hostname.strip(".").lower()
    offset = 12
    for _ in range(qdcount):
        qname, offset = _decode_dns_name(packet, offset)
        if offset + 4 > len(packet):
            return False
        qtype, qclass = struct.unpack("!HH", packet[offset : offset + 4])
        offset += 4
        if qname == target and qtype in (1, 255) and (qclass & 0x7FFF) in (1, 255):
            return True
    return False


def _default_local_ip() -> str:
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
            s.connect(("8.8.8.8", 80))
            return s.getsockname()[0]
    except Exception:
        return "127.0.0.1"


class MdnsResponder:
    """Anuncia e responde consultas mDNS UDP/5353 para um hostname .local."""

    def __init__(
        self,
        hostname: str = DEFAULT_REMOTE_HOSTNAME,
        ip_provider: Optional[Callable[[], str]] = None,
    ) -> None:
        self.hostname = hostname.strip(".").lower()
        self._ip_provider = ip_provider or _default_local_ip
        self._stop_event = threading.Event()
        self._sock: Optional[socket.socket] = None
        self._thread: Optional[threading.Thread] = None

    def start(self) -> bool:
        if self._thread is not None and self._thread.is_alive():
            return True
        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM, socket.IPPROTO_UDP)
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            if hasattr(socket, "SO_REUSEPORT"):
                try:
                    sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEPORT, 1)
                except OSError:
                    pass
            sock.bind(("", MDNS_PORT))
            local_ip = self._ip_provider()
            mreq = struct.pack(
                "4s4s",
                socket.inet_aton(MDNS_ADDR),
                socket.inet_aton(local_ip if local_ip != "127.0.0.1" else "0.0.0.0"),
            )
            try:
                sock.setsockopt(socket.IPPROTO_IP, socket.IP_ADD_MEMBERSHIP, mreq)
            except OSError:
                mreq_any = struct.pack("4s4s", socket.inet_aton(MDNS_ADDR), socket.inet_aton("0.0.0.0"))
                sock.setsockopt(socket.IPPROTO_IP, socket.IP_ADD_MEMBERSHIP, mreq_any)
            sock.setsockopt(socket.IPPROTO_IP, socket.IP_MULTICAST_TTL, 255)
            sock.settimeout(1.0)
            self._sock = sock
            self._stop_event.clear()
            self._thread = threading.Thread(target=self._serve_loop, name="SafePCKidsMdns", daemon=True)
            self._thread.start()
            self.announce()
            logger.info("mDNS ativo para http://%s", self.hostname)
            return True
        except Exception as exc:
            logger.debug("mDNS nao iniciado (%s): %s", self.hostname, exc)
            self.stop()
            return False

    def announce(self) -> None:
        if self._sock is None:
            return
        try:
            ip = self._ip_provider()
            if ip and ip != "127.0.0.1":
                payload = build_mdns_a_response(self.hostname, ip)
                self._sock.sendto(payload, (MDNS_ADDR, MDNS_PORT))
        except Exception as exc:
            logger.debug("Falha ao anunciar mDNS: %s", exc)

    def _serve_loop(self) -> None:
        while not self._stop_event.is_set() and self._sock is not None:
            try:
                data, addr = self._sock.recvfrom(2048)
            except socket.timeout:
                continue
            except OSError:
                break
            if should_answer_mdns_query(data, self.hostname):
                ip = self._ip_provider()
                if ip and ip != "127.0.0.1":
                    try:
                        payload = build_mdns_a_response(self.hostname, ip)
                        self._sock.sendto(payload, (MDNS_ADDR, MDNS_PORT))
                    except OSError:
                        pass

    def stop(self) -> None:
        self._stop_event.set()
        if self._sock is not None:
            try:
                self._sock.close()
            except OSError:
                pass
            self._sock = None
