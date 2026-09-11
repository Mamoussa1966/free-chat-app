import unittest
from providers import SEATS, _parse_models
class T(unittest.TestCase):
    def test_seats(self): self.assertEqual([s.key for s in SEATS],['openai','gemini','claude','grok','kimi'])
    def test_parser_order_and_dedupe(self): self.assertEqual(_parse_models('a,b,a，c'),('a','b','c'))
    def test_parser_rejects_space(self): self.assertEqual(_parse_models('good,bad model'),('good',))
if __name__=='__main__': unittest.main()
