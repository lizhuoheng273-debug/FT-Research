import json
from types import SimpleNamespace
import pytest
import chat

@pytest.mark.parametrize('effort',['low','high','max'])
def test_selected_effort_reaches_provider_payload(monkeypatch, effort):
    payloads=[]
    monkeypatch.setattr(chat.requests,'post',lambda *a,**kw: (payloads.append(kw['json']) or SimpleNamespace(status_code=200)))
    chat._call_llm_stream({'baseURL':'https://open.bigmodel.cn/api/paas/v4','apiKey':'test-only','model':'glm-5.3-flash','reasoningEffort':effort},[{'role':'user','content':'test'}],True)
    assert payloads[0]['reasoning_effort']==effort
    assert payloads[0]['stream'] is True

def test_background_adapter_uses_immutable_run_choice_not_prompt(tmp_path,monkeypatch):
    import app as module
    from ai_jobs import RunControl
    from session_store import SessionStore
    store=SessionStore(tmp_path/'adapter.sqlite3')
    owner=store.create_principal('owner')
    conversation=store.create_conversation(owner,'chat',{})
    cfg={'apiKey':'test-only','model':'glm-5.3-flash'}
    monkeypatch.setattr(module,'session_store',store)
    monkeypatch.setattr(module.glm_config,'load_glm_config',lambda:cfg)
    captured=[]
    def stream(config,history,context,**kwargs):
        captured.append((dict(config),json.loads(context)))
        yield {'type':'done'}
    monkeypatch.setattr(module.chat_layer,'run_chat_stream',stream)
    context={'text':'Public test context','_reasoningEffort':'high'}
    list(module._background_runner({'principal_id':owner.id,'conversation_id':conversation['id'],'question':'test','context':context},RunControl(lambda:False)))
    assert captured[0][0]['reasoningEffort']=='high'
    assert captured[0][1]=={'text':'Public test context'}
    assert 'reasoningEffort' not in cfg
    assert context['_reasoningEffort']=='high'
