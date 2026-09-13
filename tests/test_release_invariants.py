from pathlib import Path
import ast

def test_provider_exports_transcriber_helper():
    s=Path('providers.py').read_text(encoding='utf-8')
    assert 'def transcribe_audio_gemini' in s

def test_version_is_current_hotfix():
    import re
    version = Path('VERSION.txt').read_text(encoding='utf-8').strip()
    assert re.fullmatch(r'V22\.1-FINAL-EXACT-NAMES-UPDATED-HOTFIX\d+-FINAL', version)
    assert f'VERSION = "{version}"' in Path('providers.py').read_text(encoding='utf-8')

def test_main_has_unique_result_key_invariant():
    s=Path('main.py').read_text(encoding='utf-8')
    assert 'result_key = f"{request_id}:{round_no}:{seat_key}"' in s
