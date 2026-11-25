"""Testes unitarios do responder mDNS leve (controle-remoto-pckids.local)."""
from __future__ import annotations

import socket
import struct
import unittest

from safepckids.mdns_responder import (
    DEFAULT_REMOTE_HOSTNAME,
    _encode_dns_name,
    build_mdns_a_response,
    should_answer_mdns_query,
)


def _build_query(name: str, qtype: int = 1, qclass: int = 1) -> bytes:
    header = struct.pack("!HHHHHH", 0x1234, 0x0000, 1, 0, 0, 0)
    return header + _encode_dns_name(name) + struct.pack("!HH", qtype, qclass)


class TestMdnsResponder(unittest.TestCase):
    def test_matches_target_hostname_case_insensitive(self):
        q = _build_query("Controle-Remoto-PCKids.local", qtype=1)
        self.assertTrue(should_answer_mdns_query(q, DEFAULT_REMOTE_HOSTNAME))

    def test_ignores_other_hostnames_and_responses(self):
        other = _build_query("outro-pc.local", qtype=1)
        self.assertFalse(should_answer_mdns_query(other, DEFAULT_REMOTE_HOSTNAME))

        resp = build_mdns_a_response(DEFAULT_REMOTE_HOSTNAME, "192.168.0.51")
        self.assertFalse(should_answer_mdns_query(resp, DEFAULT_REMOTE_HOSTNAME))

    def test_build_response_encodes_a_record_and_ip(self):
        pkt = build_mdns_a_response(DEFAULT_REMOTE_HOSTNAME, "192.168.0.51", ttl=60)
        txid, flags, qd, an, ns, ar = struct.unpack("!HHHHHH", pkt[:12])
        self.assertEqual((txid, flags, qd, an, ns, ar), (0, 0x8400, 0, 1, 0, 0))
        self.assertTrue(pkt.endswith(socket.inet_aton("192.168.0.51")))


if __name__ == "__main__":
    unittest.main()
