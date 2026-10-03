import copy
from conversation_store import ensure_store, canonical_create_lifecycle, canonical_history_hash, hydrate_canonical_record, rebuild_runtime_indexes_from_canonical, validate_canonical_chain

def _chat():
    c={'conversation_id':'conv-test','session_id':'sess-test'}
    ensure_store(c)
    return c

def _rows(i):
    mid=f'M{i}'; rid=f'R{i}'; oid=f'O{i}'
    msg={'message_id':mid,'conversation_id':'conv-test','session_id':'sess-test','role':'user','request_id':rid,'created_at':f'2026-09-22T00:0{i}:00Z'}
    req={'request_id':rid,'conversation_id':'conv-test','session_id':'sess-test','message_id':mid,'created_at':msg['created_at'],'state':'RUNNING'}
    rnd={'round_id':oid,'conversation_id':'conv-test','session_id':'sess-test','message_id':mid,'request_id':rid,'round':1,'created_at':msg['created_at'],'status':'STARTED'}
    return msg,req,rnd

def test_atomic_two_lifecycles_and_unique_rounds():
    c=_chat(); state={}
    for i in (1,2):
        m,r,o=_rows(i)
        out=canonical_create_lifecycle(c,m,r,o,state)
        assert out['committed']
    rec=c['conversation_record']
    assert len(rec['messages'])==2 and len(rec['requests'])==2 and len(rec['rounds'])==2
    assert rec['rounds'][0]['round_id'] != rec['rounds'][1]['round_id']
    assert validate_canonical_chain(rec)['message_request_integrity']
    assert validate_canonical_chain(rec)['request_round_integrity']

def test_rerun_narrow_runtime_restores_canonical_history_and_hash():
    c=_chat(); state={}
    for i in (1,2): canonical_create_lifecycle(c,*_rows(i),state)
    canonical=c['conversation_record']
    h1=canonical_history_hash(canonical)
    c['conversation_record']=copy.deepcopy({**canonical,'messages':canonical['messages'][-1:], 'requests':canonical['requests'][-1:], 'rounds':canonical['rounds'][-1:]})
    rebuild_runtime_indexes_from_canonical(c,state)
    h2=canonical_history_hash(c['conversation_record'])
    assert len(c['conversation_record']['messages'])==2
    assert len(c['conversation_record']['requests'])==2
    assert len(c['conversation_record']['rounds'])==2
    assert h1==h2

def test_negative_without_canonical_transport_is_not_proven():
    c=_chat(); state={}
    m,r,o=_rows(1); canonical_create_lifecycle(c,m,r,o,state)
    narrowed=copy.deepcopy(c['conversation_record'])
    c['conversation_record']={**narrowed,'messages':[],'requests':[],'rounds':[]}
    empty_state={}
    hydrate_canonical_record(c,empty_state)
    rebuild_runtime_indexes_from_canonical(c,empty_state)
    assert len(c['conversation_record']['messages'])==0
    assert len(c['conversation_record']['requests'])==0
    assert len(c['conversation_record']['rounds'])==0
