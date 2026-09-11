from pathlib import Path
import ast

def test_provider_exports_transcriber_helper():
    s=Path('providers.py').read_text(encoding='utf-8')
    assert 'def get_gemini_transcriber_model' in s

def test_version_is_hotfix13():
    assert 'HOTFIX13' in Path('providers.py').read_text(encoding='utf-8')

def test_main_has_unique_result_key_invariant():
    s=Path('main.py').read_text(encoding='utf-8')
    assert 'result_key = f"{request_id}:{round_no}:{result.get(\'seat\',\'\')}"' in s
