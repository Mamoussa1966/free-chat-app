import unittest

from attachment_utils import MAX_FILES, MAX_TOTAL_BYTES, as_data_url, extract_text, normalize_uploaded_files


class FakeUpload:
    def __init__(self, name, data, mime):
        self.name = name
        self._data = data
        self.type = mime

    def getvalue(self):
        return self._data


class AttachmentTests(unittest.TestCase):
    def test_normalize_and_text_extract(self):
        item = normalize_uploaded_files([FakeUpload("note.txt", b"Hello attachment", "text/plain")])[0]
        self.assertEqual(item["name"], "note.txt")
        self.assertEqual(extract_text(item), "Hello attachment")

    def test_image_data_url(self):
        item = normalize_uploaded_files([FakeUpload("x.png", b"abc", "image/png")])[0]
        self.assertTrue(as_data_url(item).startswith("data:image/png;base64,"))

    def test_duplicate_files_are_deduplicated(self):
        files = [
            FakeUpload("same.txt", b"abc", "text/plain"),
            FakeUpload("same.txt", b"abc", "text/plain"),
        ]
        self.assertEqual(len(normalize_uploaded_files(files)), 1)

    def test_same_prefix_different_content_is_not_deduplicated(self):
        prefix = b"x" * 64
        a = prefix + b"A"
        b = prefix + b"B"
        items = normalize_uploaded_files([
            FakeUpload("same.txt", a, "text/plain"),
            FakeUpload("same.txt", b, "text/plain"),
        ])
        self.assertEqual(len(items), 2)

    def test_per_file_limit(self):
        with self.assertRaises(ValueError):
            normalize_uploaded_files([
                FakeUpload(
                    "large.bin",
                    b"x" * (10 * 1024 * 1024 + 1),
                    "application/octet-stream",
                )
            ])

    def test_total_limit(self):
        size = 10 * 1024 * 1024
        with self.assertRaises(ValueError):
            normalize_uploaded_files([
                FakeUpload("a.bin", b"a" * size, "application/octet-stream"),
                FakeUpload("b.bin", b"b" * size, "application/octet-stream"),
                FakeUpload("c.bin", b"c" * size, "application/octet-stream"),
            ])

    def test_limits_are_positive(self):
        self.assertGreater(MAX_FILES, 0)
        self.assertGreater(MAX_TOTAL_BYTES, 0)


if __name__ == "__main__":
    unittest.main()
