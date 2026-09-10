import io
import unittest
import zipfile

from attachment_utils import (
    MAX_FILES,
    MAX_TOTAL_BYTES,
    extract_text,
    normalize_uploaded_files,
)


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
        self.assertEqual(extract_text(item), "Hello attachment")
        self.assertEqual(len(item["sha256"]), 64)

    def test_duplicate_payloads_are_removed(self):
        result = normalize_uploaded_files([
            FakeUpload("a.txt", b"same", "text/plain"),
            FakeUpload("b.txt", b"same", "text/plain"),
        ])
        self.assertEqual(len(result), 1)

    def test_file_size_limit(self):
        with self.assertRaises(ValueError):
            normalize_uploaded_files([FakeUpload("big.bin", b"x" * (10 * 1024 * 1024 + 1), "application/octet-stream")])

    def test_total_limit(self):
        a = FakeUpload("a.bin", b"a" * (10 * 1024 * 1024), "application/octet-stream")
        b = FakeUpload("b.bin", b"b" * (10 * 1024 * 1024), "application/octet-stream")
        c = FakeUpload("c.bin", b"c" * (6 * 1024 * 1024), "application/octet-stream")
        with self.assertRaises(ValueError):
            normalize_uploaded_files([a, b, c])

    def test_file_count_limit(self):
        files = [FakeUpload(f"{i}.txt", str(i).encode(), "text/plain") for i in range(MAX_FILES + 1)]
        with self.assertRaises(ValueError):
            normalize_uploaded_files(files)

    def test_docx_safe_container_is_read(self):
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w") as zf:
            zf.writestr("[Content_Types].xml", "<Types/>")
            zf.writestr("word/document.xml", "<w:document><w:body><w:p>Hello DOCX</w:p></w:body></w:document>")
        item = normalize_uploaded_files([FakeUpload("x.docx", buf.getvalue(), "application/vnd.openxmlformats-officedocument.wordprocessingml.document")])[0]
        self.assertIn("Hello DOCX", extract_text(item))

    def test_docx_path_traversal_is_rejected(self):
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w") as zf:
            zf.writestr("../evil.txt", "bad")
            zf.writestr("word/document.xml", "<w:document/>")
        with self.assertRaises(ValueError):
            normalize_uploaded_files([FakeUpload("x.docx", buf.getvalue(), "application/vnd.openxmlformats-officedocument.wordprocessingml.document")])


if __name__ == "__main__":
    unittest.main()
