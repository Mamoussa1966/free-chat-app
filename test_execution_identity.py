from unittest.mock import patch
from providers import SEATS, call_seat

def test_result_model_equals_actual_call_model():
    seat=next(x for x in SEATS if x.key=='gemini')
    with patch('providers.call_official',return_value='OK') as api:
        r=call_seat(seat,'x','',1,False,'key',[],('gemini-3.8-flash','gemini-3.7-flash'),None)
    actual=api.call_args.args[2]
    assert r['executed_model']==actual==r['model']
    assert r['attempted_models']==[actual]
