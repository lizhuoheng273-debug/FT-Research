export const RSS_SUBSCRIPTIONS_STORAGE_KEY = "ft-research:ai-rss-subscriptions:v1";

export const DEFAULT_RSS_SOURCE_ORDER = [
  "ithome", "qbitai", "jiqizhixin", "zhidx", "xinzhiyuan", "36kr", "tmtpost", "huxiu", "technode", "solidot", "baijingapp", "williamlong",
] as const;

export interface RssItem {
  id: string;
  title: string;
  summary?: string;
  publishedAt?: string | null;
  originalUrl: string;
}

export interface RssSource {
  id: string;
  name: string;
  category: string;
  region: string;
  priority: number;
  homepage: string;
  lastSuccessAt?: string | null;
  stale: boolean;
  error?: string | null;
  items: RssItem[];
  url?: string;
}

export interface CustomRssSubscription {
  id: string;
  name: string;
  url: string;
}

export interface RssSubscriptionState {
  order: string[];
  pinned: string[];
  hidden: string[];
  custom: CustomRssSubscription[];
}

export const defaultRssSubscriptionState = (): RssSubscriptionState => ({ order: [...DEFAULT_RSS_SOURCE_ORDER], pinned: [], hidden: [], custom: [] });

const storage = () => (typeof window === "undefined" ? null : window.localStorage);

export function readRssSubscriptionState(): RssSubscriptionState {
  const fallback = defaultRssSubscriptionState();
  try {
    const raw = storage()?.getItem(RSS_SUBSCRIPTIONS_STORAGE_KEY);
    if (!raw) return fallback;
    const parsed = JSON.parse(raw) as Partial<RssSubscriptionState>;
    return {
      order: Array.isArray(parsed.order) ? parsed.order.filter((value): value is string => typeof value === "string") : fallback.order,
      pinned: Array.isArray(parsed.pinned) ? parsed.pinned.filter((value): value is string => typeof value === "string") : [],
      hidden: Array.isArray(parsed.hidden) ? parsed.hidden.filter((value): value is string => typeof value === "string") : [],
      custom: Array.isArray(parsed.custom) ? parsed.custom.filter((value): value is CustomRssSubscription => Boolean(value && typeof value.id === "string" && typeof value.name === "string" && typeof value.url === "string")) : [],
    };
  } catch {
    return fallback;
  }
}

export function writeRssSubscriptionState(next: RssSubscriptionState): void {
  try { storage()?.setItem(RSS_SUBSCRIPTIONS_STORAGE_KEY, JSON.stringify(next)); } catch { /* private browsing can reject storage */ }
}

export function resetSubscriptions(): RssSubscriptionState {
  const next = defaultRssSubscriptionState();
  try { storage()?.removeItem(RSS_SUBSCRIPTIONS_STORAGE_KEY); } catch { /* ignore unavailable storage */ }
  return next;
}

export function orderRssSources(sources: RssSource[], state: RssSubscriptionState): RssSource[] {
  const byId = new Map(sources.map((source) => [source.id, source]));
  const sourceOrder = [...state.order, ...sources.map((source) => source.id)].filter((id, index, all) => all.indexOf(id) === index && byId.has(id));
  const pinned = new Set(state.pinned);
  return sourceOrder.sort((a, b) => Number(pinned.has(b)) - Number(pinned.has(a))).map((id) => byId.get(id)!).filter((source) => !state.hidden.includes(source.id));
}

export function moveSubscription(state: RssSubscriptionState, sourceId: string, direction: -1 | 1): RssSubscriptionState {
  const order = [...state.order];
  const index = order.indexOf(sourceId);
  const nextIndex = index + direction;
  if (index < 0 || nextIndex < 0 || nextIndex >= order.length) return state;
  [order[index], order[nextIndex]] = [order[nextIndex], order[index]];
  return { ...state, order };
}

export function moveSubscriptionTo(state: RssSubscriptionState, sourceId: string, targetId: string): RssSubscriptionState {
  const order = [...state.order];
  const from = order.indexOf(sourceId);
  const target = order.indexOf(targetId);
  if (from < 0 || target < 0 || from === target) return state;
  const [moved] = order.splice(from, 1);
  order.splice(order.indexOf(targetId), 0, moved);
  return { ...state, order };
}

export function toggleSubscriptionFlag(state: RssSubscriptionState, key: "pinned" | "hidden", sourceId: string): RssSubscriptionState {
  const values = new Set(state[key]);
  if (values.has(sourceId)) values.delete(sourceId); else values.add(sourceId);
  return { ...state, [key]: [...values] };
}

export function addCustomSubscription(state: RssSubscriptionState, source: Pick<CustomRssSubscription, "id" | "name" | "url">): RssSubscriptionState {
  const custom = [...state.custom.filter((item) => item.id !== source.id), source];
  return { ...state, custom, order: [...state.order.filter((id) => id !== source.id), source.id] };
}

export function removeCustomSource(state: RssSubscriptionState, sourceId: string): RssSubscriptionState {
  return { ...state, custom: state.custom.filter((source) => source.id !== sourceId), order: state.order.filter((id) => id !== sourceId), pinned: state.pinned.filter((id) => id !== sourceId), hidden: state.hidden.filter((id) => id !== sourceId) };
}
