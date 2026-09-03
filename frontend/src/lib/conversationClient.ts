export type ConversationEvent = { runId: string; seq: number; type: string; payload?: Record<string, any> };
export type ConversationInput = { clientRequestId: string; question: string; context: Record<string, any> };
export type ConversationProgress = { phase: string; status: string; message: string; tool?: string; elapsedMs?: number; startedAt?: number };
export type ConversationToolUse = { name: string; arg?: string; status: string; message?: string; elapsedMs?: number };

type Api = {
  get(id: string): Promise<any>;
  start(id: string, input: ConversationInput): Promise<{ runId: string; status: string }>;
  events(runId: string, after: number, onEvent: (event: ConversationEvent) => void, signal: AbortSignal): Promise<void>;
  cancel(runId: string): Promise<any>;
};

type Message = { role: 'user' | 'assistant'; content: string; status?: string };
type State = { conversation: any; messages: Message[]; activeRunId: string | null; lastSeq: number; pending: Map<number, ConversationEvent>; listeners: Set<(state: State) => void>; abort?: AbortController; requestVersion: number; attachVersion: number; status: string; progress: ConversationProgress | null; toolUses: ConversationToolUse[]; publishTimer?: ReturnType<typeof setTimeout> };

function stateFor(states: Map<string, State>, id: string): State {
  let state = states.get(id);
  if (!state) {
    state = { conversation: { id }, messages: [], activeRunId: null, lastSeq: 0, pending: new Map(), listeners: new Set(), requestVersion: 0, attachVersion: 0, status: 'idle', progress: null, toolUses: [] };
    states.set(id, state);
  }
  return state;
}

function notify(state: State, batch = false) {
  // Store every delta immediately; only coalesce React notifications in bursts.
  // First text, progress and terminal states bypass this short render window.
  if (batch) {
    state.publishTimer ??= setTimeout(() => notify(state), 50);
    return;
  }
  if (state.publishTimer !== undefined) clearTimeout(state.publishTimer);
  state.publishTimer = undefined;
  const published = { ...state, messages: state.messages.map(message => ({ ...message })), progress: state.progress ? { ...state.progress } : null, toolUses: state.toolUses.map(tool => ({ ...tool })) };
  for (const listener of state.listeners) listener(published);
}

function mergeProgress(state: State, payload: Record<string, any>) {
  // Older runs stored progress inside payload.payload; preserve their replay.
  const next = { ...(payload.payload || payload) } as ConversationProgress;
  if (next.status === 'running') {
    const previous = state.progress;
    next.startedAt = previous?.phase === next.phase && previous.tool === next.tool && previous.status === 'running' ? previous.startedAt : Date.now();
  }
  state.progress = next;
  if (next.phase !== 'tool' || !next.tool) return;
  const index = state.toolUses.findIndex(tool => tool.name === next.tool);
  const tool = { name: next.tool, status: next.status, message: next.message, elapsedMs: next.elapsedMs };
  if (index < 0) state.toolUses.push(tool);
  else state.toolUses[index] = { ...state.toolUses[index], ...tool };
}

export function createConversationClient(api: Api) {
  const states = new Map<string, State>();

  const failStream = (state: State, runId: string) => {
    if (state.activeRunId !== runId) return;
    state.status = 'error';
    state.progress = null;
    state.activeRunId = null;
    state.attachVersion++;
    const last = state.messages[state.messages.length - 1];
    if (last?.role === 'assistant') last.status = 'error';
    notify(state);
  };

  const attach = (conversationId: string, listener: (state: State) => void) => {
    const state = stateFor(states, conversationId);
    const attachVersion = ++state.attachVersion;
    state.listeners.add(listener);
    void api.get(conversationId).then((detail) => {
      if (!states.has(conversationId) || state.attachVersion !== attachVersion) return;
      if (!state.messages.length) state.messages = (detail.messages || []).filter((m: any) => m.role === 'user' || m.role === 'assistant').map((m: any) => ({ role: m.role, content: m.content, status: m.status }));
      state.conversation = detail.conversation || state.conversation;
      const previousRunId = state.activeRunId;
      const activeRunId = previousRunId || detail.activeRunId;
      if (activeRunId !== previousRunId) { state.lastSeq = 0; state.pending.clear(); }
      state.activeRunId = activeRunId;
      if (activeRunId) {
        const last = state.messages[state.messages.length - 1];
        if (last?.role !== 'assistant' || last.status !== 'partial') state.messages.push({ role: 'assistant', content: '', status: 'partial' });
        state.status = 'running';
        if (!state.abort || state.abort.signal.aborted) subscribe(state, activeRunId);
      }
      notify(state);
    }).catch(() => undefined);
    return () => { state.listeners.delete(listener); };
  };

  const subscribe = (state: State, runId: string, retriesLeft = 1) => {
    state.abort?.abort();
    const controller = new AbortController();
    state.abort = controller;
    let terminalSeen = false;
    const clearController = () => {
      if (state.abort === controller) state.abort = undefined;
    };
    void api.events(runId, state.lastSeq, (event) => {
      if (event.runId !== state.activeRunId || event.seq <= state.lastSeq || state.pending.has(event.seq)) return;
      if (event.type === 'done' || event.type === 'stopped' || event.type === 'error' || event.type === 'interrupted') terminalSeen = true;
      state.pending.set(event.seq, event);
      while (state.pending.has(state.lastSeq + 1)) {
        const next = state.pending.get(state.lastSeq + 1)!;
        state.pending.delete(next.seq);
        state.lastSeq = next.seq;
        const payload = next.payload || {};
        let batch = false;
        if (next.type === 'progress') {
          mergeProgress(state, payload);
        } else if (next.type === 'tool') {
          mergeProgress(state, { phase: 'tool', status: 'running', tool: payload.tool || (next as any).tool, message: payload.message || `正在调用：${payload.tool || (next as any).tool}` });
        } else if (next.type === 'delta') {
          const last = state.messages[state.messages.length - 1];
          batch = Boolean(last?.content);
          if (last?.role === 'assistant') last.content += String(payload.text || '');
          if (!state.progress || state.progress.phase !== 'model') mergeProgress(state, { phase: 'model', status: 'running', message: '模型输出中…' });
        } else if (next.type === 'done') {
          state.status = 'completed'; state.activeRunId = null; state.progress = null; state.attachVersion++;
          const last = state.messages[state.messages.length - 1]; if (last?.role === 'assistant') last.status = 'complete';
        } else if (next.type === 'stopped' || next.type === 'error' || next.type === 'interrupted') {
          state.status = next.type; state.activeRunId = null; state.progress = null; state.attachVersion++;
          const last = state.messages[state.messages.length - 1]; if (last?.role === 'assistant') last.status = next.type;
        }
        notify(state, batch);
      }
    }, controller.signal).then(() => {
      if (controller.signal.aborted || state.activeRunId !== runId) { clearController(); return; }
      if (!terminalSeen && retriesLeft > 0) { clearController(); subscribe(state, runId, retriesLeft - 1); return; }
      if (!terminalSeen) failStream(state, runId);
      clearController();
    }).catch((error: any) => {
      if (controller.signal.aborted || state.activeRunId !== runId) { clearController(); return; }
      if (retriesLeft > 0 && ![401, 403, 404].includes(error?.status)) { clearController(); subscribe(state, runId, retriesLeft - 1); return; }
      failStream(state, runId);
      clearController();
    });
  };

  const send = async (conversationId: string, input: ConversationInput) => {
    const state = stateFor(states, conversationId);
    if (!input.question.trim()) return;
    const requestVersion = ++state.requestVersion;
    state.attachVersion++;
    state.abort?.abort();
    const previous = state.messages[state.messages.length - 1];
    if (state.status === 'running' && previous?.role === 'assistant' && previous.status === 'partial') previous.status = 'stopped';
    const assistantMessage: Message = { role: 'assistant', content: '', status: 'partial' };
    state.messages.push({ role: 'user', content: input.question }, assistantMessage);
    state.status = 'running';
    state.progress = { phase: 'submit', status: 'running', message: '正在提交请求…', startedAt: Date.now() };
    state.toolUses = [];
    notify(state);
    let result;
    try {
      result = await api.start(conversationId, input);
    } catch (error) {
      if (state.requestVersion === requestVersion) {
        state.status = 'error'; state.activeRunId = null; state.progress = null;
        assistantMessage.status = 'error'; notify(state);
      }
      throw error;
    }
    if (state.requestVersion !== requestVersion) {
      assistantMessage.status = 'stopped';
      notify(state);
      void api.cancel(result.runId).catch(() => undefined);
      return;
    }
    state.activeRunId = result.runId;
    state.status = result.status;
    state.progress = { phase: 'queue', status: 'running', message: result.status === 'queued' ? '请求已接收，等待处理…' : '请求已接收，正在分析…', startedAt: Date.now() };
    state.lastSeq = 0;
    state.pending.clear();
    notify(state);
    subscribe(state, result.runId);
  };

  const stop = async (conversationId: string) => {
    const state = stateFor(states, conversationId);
    const requestVersion = ++state.requestVersion;
    state.attachVersion++;
    const runId = state.activeRunId;
    if (!runId) {
      if (state.status === 'running') {
        state.status = 'stopped';
        state.progress = null;
        const last = state.messages[state.messages.length - 1];
        if (last?.role === 'assistant') last.status = 'stopped';
        notify(state);
      }
      return;
    }
    await api.cancel(runId);
    if (state.requestVersion !== requestVersion || state.activeRunId !== runId) return;
    state.abort?.abort();
    state.activeRunId = null;
    state.status = 'stopped';
    state.progress = null;
    const last = state.messages[state.messages.length - 1];
    if (last?.role === 'assistant') last.status = 'stopped';
    notify(state);
  };

  const resetIdentity = () => {
    for (const state of states.values()) { state.abort?.abort(); clearTimeout(state.publishTimer); state.listeners.clear(); }
    states.clear();
  };

  const snapshot = (conversationId: string) => {
    const state = stateFor(states, conversationId);
    return { conversation: state.conversation, messages: state.messages.map((message) => ({ ...message })), activeRunId: state.activeRunId, status: state.status, lastSeq: state.lastSeq, progress: state.progress ? { ...state.progress } : null, toolUses: state.toolUses.map(tool => ({ ...tool })) };
  };

  return { attach, send, stop, resetIdentity, snapshot };
}
