import os
from unittest.mock import patch
from providers import SEATS, get_model_candidates

def test_secret_has_precedence_for_exact_key():
    with patch('providers._streamlit_secret_state', return_value=(True, 'm-secret')):
        with patch.dict(os.environ, {'GEMINI_FREE_MODELS':'m-env'}, clear=False):
            gemini=next(x for x in SEATS if x.key=='gemini')
            assert get_model_candidates(gemini)==('m-secret',)
