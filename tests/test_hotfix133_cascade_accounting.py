from main import _authoritative_request_metrics

def test_hotfix133_counts_failed_and_successful_runtime_attempts():
    rid="REQ"
    results=[
      {"seat":"gemini","name":"Gemini","request_id":rid,"round":1,"request_routed":True,"model_candidates_configured":True,"status":"SUCCESS","content":"ok",
       "runtime_execution_events":[
         {"execution_started":True,"attempt":1,"model":"g1"},
         {"execution_started":True,"attempt":2,"model":"g2"},
         {"execution_started":True,"attempt":3,"model":"g3"}]},
      {"seat":"deepseek","name":"DeepSeek","request_id":rid,"round":1,"request_routed":True,"model_candidates_configured":True,"status":"SUCCESS","content":"ok",
       "runtime_execution_events":[{"execution_started":True,"attempt":1,"model":"d1"}]},
    ]
    m=_authoritative_request_metrics(rid,results,[])
    assert m["total_cascade_attempts"]==4
    assert m["attempts_by_provider"]=={"Gemini":3,"DeepSeek":1}

def test_hotfix133_ignores_non_runtime_rows():
    rid="REQ"
    results=[{"seat":"gemini","name":"Gemini","request_id":rid,"round":1,"request_routed":True,"model_candidates_configured":True,"status":"PROVIDER_ERROR","content":"","attempt_telemetry":[{"attempt":1,"model":"g1","execution_started":False}],"runtime_execution_events":[]}]
    m=_authoritative_request_metrics(rid,results,[])
    assert m["total_cascade_attempts"]==0
