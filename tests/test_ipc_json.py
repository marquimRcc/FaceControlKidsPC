import unittest

from facekids.ipc_json import parse_local_json


class StrictLocalJsonTests(unittest.TestCase):
    def test_valid_payload_and_nested_data(self):
        value = parse_local_json(
            '{"status":"ALLOW","data":{"child_id":2,"remaining":120},'
            '"child_id":2,"timestamp":1234}'
        )
        self.assertEqual(value["data"]["child_id"], 2)
        self.assertEqual(value["child_id"], 2)

    def test_duplicate_keys_at_each_depth_rejected(self):
        for text in (
            '{"status":"ALLOW","status":"DENY_UNKNOWN"}',
            '{"data":{"child_id":1,"child_id":2}}',
            '{"data":[{"value":1,"value":2}]}',
            '{"timestamp":1,"timestamp":2}',
        ):
            with self.subTest(text=text), self.assertRaises(ValueError):
                parse_local_json(text)

    def test_reject_nonfinite_invalid_encoding_and_extra_json(self):
        for text in (
            '{"timestamp":NaN}',
            '{"remaining":Infinity}',
            '{"remaining":-Infinity}',
            '{}{}',
            '{"child_id":2',
            '',
        ):
            with self.subTest(text=text), self.assertRaises(ValueError):
                parse_local_json(text)
        with self.assertRaises(UnicodeDecodeError):
            parse_local_json(b'{"name":"\xff"}')

    def test_size_limit_in_bytes_not_codepoints(self):
        with self.assertRaises(ValueError):
            parse_local_json('{"x":"' + "é" * 1020 + '"}', max_bytes=2047)
        self.assertEqual(parse_local_json('{"child_id":2}')["child_id"], 2)
        with self.assertRaises(ValueError):
            parse_local_json('{"child_id":2}', max_bytes=8)

    def test_reject_unexpected_types(self):
        for value in (None, 2, {}, [], True):
            with self.assertRaises(ValueError):
                parse_local_json(value)


if __name__ == "__main__":
    unittest.main()
