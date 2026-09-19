from pathlib import Path

def test_round_display_uses_execution_identity():
    s=Path('main.py').read_text(encoding='utf-8')
    assert "message.get('executed_model') or message.get('model', '')" in s

def test_result_line_uses_execution_identity():
    s=Path('main.py').read_text(encoding='utf-8')
    assert "result.get('executed_model') or result['model']" in s

def test_duplicate_request_round_seat_is_persisted_once():
    import sys, types
    from unittest.mock import patch
    sys.modules.setdefault('streamlit', types.ModuleType('streamlit'))
    from main import _run_council
    from providers import SEATS
    chat={'messages':[],'result_keys':[]}
    r={'seat':'gemini','name':'Gemini','label':'🔑 Gemini','status':'SUCCESS','mode':'official','model':'m1','executed_model':'m1','content':'ok','attempted_models':['m1'],'request_id':'RID','round':1}
    with patch('main._run_round',return_value=[r,dict(r)]):
        out=_run_council('x',chat,1,{},[],{'gemini':('m1',)},'u','RID')
    assert len(out)==1
    assert len(chat['messages'])==1
    assert len(chat['result_keys'])==1
