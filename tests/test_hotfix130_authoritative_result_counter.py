from main import _authoritative_ui_projection, _format_authoritative_counter_summary

def record():
    rid='AUTH-RID-130'
    return {'request_id':rid,'results':[
        {'status':'SUCCESS','seat':'gemini'},{'status':'SUCCESS','seat':'deepseek'},
        {'status':'DISPATCH_REJECTED','seat':'claude'},{'status':'DISPATCH_REJECTED','seat':'grok'},
        {'status':'NOT_CONFIGURED','seat':'chatgpt'},{'status':'NOT_CONFIGURED','seat':'kimi'}],
        'request_metrics':{'request_id':rid,'configured_seats':4,'requested_seats':4,'executed_seats':2,'successful_seats':2,'total_cascade_attempts':2,'provider_execution_events':2}}

def test_authoritative_projection():
    c=_authoritative_ui_projection({'request_records':[record()]},'AUTH-RID-130')
    assert (c['configured'],c['requested'],c['executed'],c['success'],c['dispatch_rejected'],c['provider_error'],c['not_configured'],c['cascade_attempts'])==(4,4,2,2,2,0,2,2)
    assert c['request_id']=='AUTH-RID-130'

def test_no_generic_failed_summary():
    c=_authoritative_ui_projection({'request_records':[record()]},'AUTH-RID-130')
    s=_format_authoritative_counter_summary(c)
    assert 'DISPATCH_REJECTED 2' in s and 'NOT_CONFIGURED 2' in s and 'SUCCESS 2' in s
    assert 'failed' not in s.lower() and 'successful' not in s.lower()
