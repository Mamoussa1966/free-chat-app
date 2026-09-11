import unittest
from attachment_utils import MAX_FILES, MAX_TOTAL_BYTES, normalize_uploaded_files, extract_text
class U:
    def __init__(self,n,d,m): self.name=n; self._d=d; self.type=m
    def getvalue(self): return self._d
class T(unittest.TestCase):
    def test_text(self):
        x=normalize_uploaded_files([U('a.txt',b'hello','text/plain')])[0]; self.assertEqual(extract_text(x),'hello')
    def test_duplicate(self): self.assertEqual(len(normalize_uploaded_files([U('a.txt',b'x','text/plain'),U('b.txt',b'x','text/plain')])),1)
    def test_limits(self): self.assertGreater(MAX_FILES,0); self.assertGreater(MAX_TOTAL_BYTES,0)
if __name__=='__main__': unittest.main()
