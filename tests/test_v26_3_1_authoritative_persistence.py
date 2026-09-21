import sys, types
sys.modules.setdefault('streamlit', types.SimpleNamespace(session_state={}))
from conversation_persistence_v26 import persist_identity, authoritative_history

def test_two_message_chain_is_authoritative():
    chat={'conversation_id':'conv','session_id':'sess'}; state={}
    rows=[]
    for i,ts in ((1,'2026-09-21T01:00:00'),(2,'2026-09-21T01:02:00')):
        m=f'm{i}'; r=f'r{i}'; q=f'conv:{r}:r1'
        persist_identity(chat,state,message={'message_id':m,'role':'user','request_id':r,'conversation_id':'conv','session_id':'sess','created_at':ts},request={'request_id':r,'message_id':m,'conversation_id':'conv','session_id':'sess','created_at':ts},round_row={'round_id':q,'request_id':r,'message_id':m,'round':1})
    h=authoritative_history(state,'conv')
    assert len(h['messages']) == len(h['requests']) == len(h['rounds']) == 2
    assert {x['request_id'] for x in h['requests']} == {'r1','r2'}
    assert all(any(q['request_id']==r['request_id'] and q['message_id']==r['message_id'] and q['round']==1 for q in h['rounds']) for r in h['requests'])

def test_narrower_current_ledger_cannot_reduce_history():
    chat={'conversation_id':'conv'}; state={}
    for i in (1,2):
        persist_identity(chat,state,message={'message_id':f'm{i}','role':'user','request_id':f'r{i}'},request={'request_id':f'r{i}','message_id':f'm{i}'})
    h=authoritative_history(state,'conv')
    assert [x['request_id'] for x in h['requests']] == ['r1','r2']
