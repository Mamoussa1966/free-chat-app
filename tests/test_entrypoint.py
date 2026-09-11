import ast
from pathlib import Path
def test_main_defines_run_app():
    tree=ast.parse(Path('main.py').read_text(encoding='utf-8'))
    assert any(isinstance(n,ast.FunctionDef) and n.name=='run_app' for n in tree.body)
