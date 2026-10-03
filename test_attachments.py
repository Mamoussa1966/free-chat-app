import io
import unittest
import zipfile
from attachment_utils import MAX_FILES, MAX_TOTAL_BYTES, extract_text, normalize_uploaded_files

class FakeUpload:
    def __init__(self, name, data, mime): self.name, self._data, self.type = name, data, mime
    def getvalue(self): return self._data

class AttachmentTests(unittest.TestCase):
    def test_text_and_hash(self):
        item = normalize_uploaded_files([FakeUpload("note.txt", b"Hello", "text/plain")])[0]
        self.assertEqual(extract_text(item), "Hello")
        self.assertEqual(len(item["sha256"]), 64)
    def test_duplicates_removed(self):
        self.assertEqual(len(normalize_uploaded_files([FakeUpload("a.txt", b"same", "text/plain"), FakeUpload("b.txt", b"same", "text/plain")])), 1)
    def test_file_limit(self):
        with self.assertRaises(ValueError): normalize_uploaded_files([FakeUpload("big.bin", b"x" * (10 * 1024 * 1024 + 1), "application/octet-stream")])
    def test_total_limit(self):
        files = [FakeUpload("a.bin", b"a" * (10 * 1024 * 1024), "application/octet-stream"), FakeUpload("b.bin", b"b" * (10 * 1024 * 1024), "application/octet-stream"), FakeUpload("c.bin", b"c" * (6 * 1024 * 1024), "application/octet-stream")]
        with self.assertRaises(ValueError): normalize_uploaded_files(files)
    def test_count_limit(self):
        with self.assertRaises(ValueError): normalize_uploaded_files([FakeUpload(str(i), str(i).encode(), "text/plain") for i in range(MAX_FILES + 1)])
    def test_docx_safe(self):
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w") as zf:
            zf.writestr("[Content_Types].xml", "<Types/>")
            zf.writestr("word/document.xml", "<w:document><w:body><w:p>Hello DOCX</w:p></w:body></w:document>")
        item = normalize_uploaded_files([FakeUpload("x.docx", buf.getvalue(), "application/vnd.openxmlformats-officedocument.wordprocessingml.document")])[0]
        self.assertIn("Hello DOCX", extract_text(item))
    def test_docx_traversal_rejected(self):
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w") as zf:
            zf.writestr("../evil.txt", "evil")
            zf.writestr("word/document.xml", "<x/>")
        with self.assertRaises(ValueError): normalize_uploaded_files([FakeUpload("x.docx", buf.getvalue(), "application/vnd.openxmlformats-officedocument.wordprocessingml.document")])
    def test_image_magic_mismatch_rejected(self):
        with self.assertRaises(ValueError): normalize_uploaded_files([FakeUpload("x.png", b"not-a-png", "image/png")])

if __name__ == "__main__": unittest.main()
