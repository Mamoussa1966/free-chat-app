import unittest
from pathlib import Path

class ReleaseInvariantTests(unittest.TestCase):
    def test_hotfix13_marker_present(self):
        self.assertIn('HOTFIX13', Path('main.py').read_text(encoding='utf-8'))
        self.assertIn('HOTFIX13', Path('providers.py').read_text(encoding='utf-8'))
    def test_no_local_engine_contract(self):
        text=Path('main.py').read_text(encoding='utf-8')
        self.assertNotIn('generate_local',text)
        self.assertNotIn('from local_engine import',text)

if __name__=='__main__': unittest.main()
