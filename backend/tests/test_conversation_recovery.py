from ai_jobs import RunManager
from ai_limits import Limits
from session_store import SessionStore


def test_upstream_exception_keeps_visible_partial_history(tmp_path):
    store=SessionStore(tmp_path/'sessions.sqlite3')
    owner=store.create_principal('owner')
    conversation=store.create_conversation(owner,'chat',{})
    def runner(run,control):
        yield {'type':'delta','payload':{'text':'partial answer'}}
        raise ConnectionError('offline')
    manager=RunManager(store,runner,Limits(store),store.clock)
    run=manager.submit(owner,conversation['id'],'r1','question',{})
    manager.shutdown()
    messages=store.get_messages(owner,conversation['id'])
    assert [m['content'] for m in messages]==['question','partial answer']
    assert messages[-1]['status']=='failed'
    assert store.events_after(owner,run['id'])[-1]['type']=='error'


def test_recovery_is_idempotent_and_restores_partial_events(tmp_path):
    store=SessionStore(tmp_path/'sessions.sqlite3')
    owner=store.create_principal('owner')
    conversation=store.create_conversation(owner,'chat',{})
    run=store.create_run(owner,conversation['id'],'r1','question',{})
    store.append_event(run['id'],'delta',{'text':'partial'})
    assert store.get_messages(owner,conversation['id'])[0]['content']=='question'
    store.recover_interrupted();store.recover_interrupted()
    assert [m['content'] for m in store.get_messages(owner,conversation['id'])]==['question','partial']
    assert store.events_after(owner,run['id'])[-1]['type']=='interrupted'


def test_pagination_keeps_equal_timestamp_rows(tmp_path):
    store=SessionStore(tmp_path/'sessions.sqlite3',clock=lambda:1800000000)
    owner=store.create_principal('owner')
    for i in range(4):store.create_conversation(owner,'chat',{},str(i))
    first=store.list_conversations(owner,limit=2)
    second=store.list_conversations(owner,limit=2,cursor=first['nextCursor'])
    assert len({i['id'] for i in first['items']+second['items']})==4
