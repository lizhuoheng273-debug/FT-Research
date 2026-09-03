export type ConversationEvent = { runId: string; seq: number; type: string; payload?: Record<string, any> };
export type ConversationInput = { clientRequestId: string; question: string; context: Record<string, any> };

type Api = {
  get(id: string): Promise<any>;
  start(id: string, input: ConversationInput): Promise<{ runId: string; status: string }>;
  events(runId: string, after: number, onEvent: (event: ConversationEvent) => void, signal: AbortSignal): Promise<void>;
  cancel(runId: string): Promise<any>;
};

type Message = { role: 'user' | 'assistant'; content: string; status?: string };
type State = { conversation: any; messages: Message[]; activeRunId: string | null; lastSeq: number; pending: Map<number, ConversationEvent>; listeners: Set<(state: State) => void>; abort?: AbortController; status: string };

function stateFor(states: Map<string, State>, id: string): State {
  let state = states.get(id);
  if (!state) {
    state = { conversation: { id }, messages: [], activeRunId: null, lastSeq: 0, pending: new Map(), listeners: new Set(), status: 'idle' };
    states.set(id, state);
  }
  return state;
}

function notify(state: State) {
  for (const listener of state.listeners) listener(state);
}

export function createConversationClient(api: Api) {
  const states = new Map<string, State>();

  const attach = (conversationId: string, listener: (state: State) => void) => {
    const state = stateFor(states, conversationId);
    state.listeners.add(listener);
    void api.get(conversationId).then((detail) => {
      if (!states.has(conversationId)) return;
      if (!state.messages.length) state.messages = (detail.messages || []).filter((m: any) => m.role === 'user' || m.role === 'assistant').map((m: any) => ({ role: m.role, content: m.content, status: m.status }));
      state.conversation = detail.conversation || state.conversation;
      state.activeRunId = detail.activeRunId || state.activeRunId;
      notify(state);
    }).catch(() => undefined);
    return () => { state.listeners.delete(listener); };
  };

  const subscribe = (state: State, runId: string) => {
    state.abort?.abort();
    const controller = new AbortController();
    state.abort = controller;
    void api.events(runId, state.lastSeq, (event) => {
      if (event.runId !== state.activeRunId || event.seq <= state.lastSeq || state.pending.has(event.seq)) return;
      state.pending.set(event.seq, event);
      while (state.pending.has(state.lastSeq + 1)) {
        const next = state.pending.get(state.lastSeq + 1)!;
        state.pending.delete(next.seq);
        state.lastSeq = next.seq;
        const payload = next.payload || {};
        if (next.type === 'delta') {
          const last = state.messages[state.messages.length - 1];
          if (last?.role === 'assistant') last.content += String(payload.text || '');
        } else if (next.type === 'done') {
          state.status = 'completed'; state.activeRunId = null;
          const last = state.messages[state.messages.length - 1]; if (last?.role === 'assistant') last.status = 'complete';
        } else if (next.type === 'stopped' || next.type === 'error' || next.type === 'interrupted') {
          state.status = next.type; state.activeRunId = null;
          const last = state.messages[state.messages.length - 1]; if (last?.role === 'assistant') last.status = next.type;
        }
        notify(state);
      }
    }, controller.signal).catch(() => undefined);
  };

  const send = async (conversationId: string, input: ConversationInput) => {
    const state = stateFor(states, conversationId);
    if (!input.question.trim()) return;
    state.messages.push({ role: 'user', content: input.question }, { role: 'assistant', content: '', status: 'partial' });
    state.status = 'running';
    notify(state);
    const result = await api.start(conversationId, input);
    state.activeRunId = result.runId;
    state.status = result.status;
    state.lastSeq = 0;
    state.pending.clear();
    subscribe(state, result.runId);
  };

  const stop = async (conversationId: string) => {
    const state = stateFor(states, conversationId);
    if (!state.activeRunId) return;
    const runId = state.activeRunId;
    await api.cancel(runId);
    state.abort?.abort();
    state.activeRunId = null;
    state.status = 'stopped';
    const last = state.messages[state.messages.length - 1];
    if (last?.role === 'assistant') last.status = 'stopped';
    notify(state);
  };

  const resetIdentity = () => {
    for (const state of states.values()) { state.abort?.abort(); state.listeners.clear(); }
    states.clear();
  };

  const snapshot = (conversationId: string) => {
    const state = stateFor(states, conversationId);
    return { conversation: state.conversation, messages: state.messages.map((message) => ({ ...message })), activeRunId: state.activeRunId, status: state.status, lastSeq: state.lastSeq };
  };

  return { attach, send, stop, resetIdentity, snapshot };
}
