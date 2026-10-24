import unittest

from facekids.pipe_protocol import decode_pipe_command


class PipeCommandProtocolTests(unittest.TestCase):
    def test_current_clients_remain_compatible(self):
        for payload, expected in (
            (b"AUTH_QUERY\n", "AUTH_QUERY"),
            (b"AUTH_QUERY\r\n", "AUTH_QUERY"),
            (b"AUTH_QUERY", "AUTH_QUERY"),
            (b"QUERY", "QUERY"),
            (b"PING", "PING"),
        ):
            with self.subTest(payload=payload):
                self.assertEqual(decode_pipe_command(payload), (expected, None))

    def test_reject_NUL_invalid_utf8_and_truncated_commands(self):
        for payload in (
            b"AUTH_QUERY\x00PING",
            b"AUTH_QUERY\x00",
            b"AUTH_QUERY\xff",
            b"AUTH_QUE",
            b"AUTH_QUERY\nPING",
            b" AUTH_QUERY",
            b"AUTH_QUERY ",
            b"AUTH_QUERY\t",
            b"AUTH_QUERY\n\n",
            b"",
            b"AUTH_QUERY" + b"X" * 600,
        ):
            with self.subTest(payload=payload):
                command, error = decode_pipe_command(payload)
                self.assertIsNone(command)
                self.assertIsNotNone(error)

    def test_binary_wrong_types_rejected(self):
        for payload in (None, "AUTH_QUERY", bytearray(b"PING"), 123):
            self.assertEqual(decode_pipe_command(payload), (None, "INVALID_REQUEST"))

    def test_unknown_ascii_command_does_not_execute(self):
        self.assertEqual(decode_pipe_command(b"DELETE"), (None, "INVALID_COMMAND"))


if __name__ == "__main__":
    unittest.main()
