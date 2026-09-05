def test_app_imports_run_app():
    text = open('app.py', encoding='utf-8').read()
    assert 'from main import run_app' in text
    assert 'if __name__' in text
