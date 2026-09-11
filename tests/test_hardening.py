from pathlib import Path
def test_no_local_engine_contract():
    s=Path('main.py').read_text(encoding='utf-8')
    assert 'Local Engine: غير مستخدم' in s
def test_execution_identity_is_rendered():
    s=Path('main.py').read_text(encoding='utf-8')
    assert 'executed_model' in s
