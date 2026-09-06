export const RSS_SUBSCRIPTIONS_STORAGE_KEY = "ft-research:ai-rss-subscriptions:v2";
const LEGACY_RSS_SUBSCRIPTIONS_STORAGE_KEY = "ft-research:ai-rss-subscriptions:v1";

export const DEFAULT_RSS_SOURCE_ORDER = [
  "ithome", "qbitai", "jiqizhixin", "zhidx", "xinzhiyuan", "tmtpost", "huxiu", "solidot", "baijingapp", "williamlong",
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
  lastAttemptAt?: string | null;
  stale: boolean;
  staleReason?: "ttl" | "fetch_failed" | null;
  error?: string | null;
  errorCode?: "timeout" | "http" | "parse" | "security" | "unknown" | null;
  items: RssItem[];
  url?: string;
}

export interface CustomRssSubscription {
  id: string;
  name: string;
  url: string;
}

export interface RssTrashEntry {
  id: string;
  kind: "builtin" | "custom";
  previousIndex: number;
  wasPinned: boolean;
  custom?: CustomRssSubscription;
}

export interface RssSubscriptionState {
  version: 2;
  order: string[];
  pinned: string[];
  custom: CustomRssSubscription[];
  trash: RssTrashEntry[];
}

interface LegacyRssSubscriptionState {
  order?: unknown;
  pinned?: unknown;
  hidden?: unknown;
  custom?: unknown;
}

export const defaultRssSubscriptionState = (): RssSubscriptionState => ({
  version: 2,
  order: [...DEFAULT_RSS_SOURCE_ORDER],
  pinned: [],
  custom: [],
  trash: [],
});

const storage = () => (typeof window === "undefined" ? null : window.localStorage);

const isRecord = (value: unknown): value is Record<string, unknown> => Boolean(value && typeof value === "object" && !Array.isArray(value));

const uniqueStrings = (value: unknown): string[] => {
  if (!Array.isArray(value)) return [];
  return [...new Set(value.filter((item): item is string => typeof item === "string"))];
};

const isCustomSubscription = (value: unknown): value is CustomRssSubscription => (
  isRecord(value) && typeof value.id === "string" && typeof value.name === "string" && typeof value.url === "string"
);

const uniqueCustomSubscriptions = (value: unknown): CustomRssSubscription[] => {
  if (!Array.isArray(value)) return [];
  const seen = new Set<string>();
  return value.filter((item): item is CustomRssSubscription => {
    if (!isCustomSubscription(item) || seen.has(item.id)) return false;
    seen.add(item.id);
    return true;
  }).map((item) => ({ ...item }));
};

const normalizeTrashEntries = (value: unknown): RssTrashEntry[] | null => {
  if (!Array.isArray(value)) return null;
  const seen = new Set<string>();
  const entries: RssTrashEntry[] = [];
  for (const item of value) {
    if (!isRecord(item) || typeof item.id !== "string") return null;
    if (seen.has(item.id)) continue;
    if (item.kind !== "builtin" && item.kind !== "custom") return null;
    if (typeof item.previousIndex !== "number" || !Number.isFinite(item.previousIndex)) return null;
    if (typeof item.wasPinned !== "boolean") return null;
    if (item.kind === "custom" && (!isCustomSubscription(item.custom) || item.custom.id !== item.id)) return null;
    seen.add(item.id);
    entries.push({
      id: item.id,
      kind: item.kind,
      previousIndex: Math.max(0, Math.floor(item.previousIndex)),
      wasPinned: item.wasPinned,
      ...(item.kind === "custom" && isCustomSubscription(item.custom) ? { custom: { ...item.custom } } : {}),
    });
  }
  return entries;
};

const normalizeV2State = (parsed: unknown): RssSubscriptionState | null => {
  if (!isRecord(parsed) || parsed.version !== 2 || !Array.isArray(parsed.order) || !Array.isArray(parsed.pinned) || !Array.isArray(parsed.custom) || !Array.isArray(parsed.trash)) return null;
  const trash = normalizeTrashEntries(parsed.trash);
  if (!trash) return null;
  const trashedIds = new Set(trash.map((entry) => entry.id));
  return {
    version: 2,
    order: uniqueStrings(parsed.order).filter((id) => !trashedIds.has(id)),
    pinned: uniqueStrings(parsed.pinned).filter((id) => !trashedIds.has(id)),
    custom: uniqueCustomSubscriptions(parsed.custom).filter((source) => !trashedIds.has(source.id)),
    trash,
  };
};

const migrateV1State = (parsed: unknown): RssSubscriptionState | null => {
  if (!isRecord(parsed)) return null;
  const legacy = parsed as LegacyRssSubscriptionState;
  if (legacy.order !== undefined && !Array.isArray(legacy.order)) return null;
  if (legacy.pinned !== undefined && !Array.isArray(legacy.pinned)) return null;
  if (legacy.hidden !== undefined && !Array.isArray(legacy.hidden)) return null;
  if (legacy.custom !== undefined && !Array.isArray(legacy.custom)) return null;
  const order = legacy.order === undefined ? [...DEFAULT_RSS_SOURCE_ORDER] : uniqueStrings(legacy.order);
  const pinned = uniqueStrings(legacy.pinned);
  const custom = uniqueCustomSubscriptions(legacy.custom);
  const customById = new Map(custom.map((source) => [source.id, source]));
  const hidden = uniqueStrings(legacy.hidden);
  const hiddenIds = new Set(hidden);
  const trash = hidden.map((id): RssTrashEntry => {
    const customSource = customById.get(id);
    const positionInOrder = order.indexOf(id);
    const defaultPosition = DEFAULT_RSS_SOURCE_ORDER.indexOf(id as typeof DEFAULT_RSS_SOURCE_ORDER[number]);
    return {
      id,
      kind: customSource ? "custom" : "builtin",
      previousIndex: Math.max(0, positionInOrder >= 0 ? positionInOrder : (defaultPosition >= 0 ? defaultPosition : order.length)),
      wasPinned: pinned.includes(id),
      ...(customSource ? { custom: { ...customSource } } : {}),
    };
  });
  return {
    version: 2,
    order: order.filter((id) => !hiddenIds.has(id)),
    pinned: pinned.filter((id) => !hiddenIds.has(id)),
    custom: custom.filter((source) => !hiddenIds.has(source.id)),
    trash,
  };
};

export function readRssSubscriptionState(): RssSubscriptionState {
  const fallback = defaultRssSubscriptionState();
  try {
    const disk = storage();
    const rawV2 = disk?.getItem(RSS_SUBSCRIPTIONS_STORAGE_KEY);
    if (rawV2 !== null && rawV2 !== undefined) {
      const parsed = normalizeV2State(JSON.parse(rawV2));
      return parsed ?? fallback;
    }
    const rawV1 = disk?.getItem(LEGACY_RSS_SUBSCRIPTIONS_STORAGE_KEY);
    if (!rawV1) return fallback;
    const migrated = migrateV1State(JSON.parse(rawV1));
    if (!migrated) return fallback;
    writeRssSubscriptionState(migrated);
    return migrated;
  } catch {
    return fallback;
  }
}

export function writeRssSubscriptionState(next: RssSubscriptionState): void {
  try { storage()?.setItem(RSS_SUBSCRIPTIONS_STORAGE_KEY, JSON.stringify(next)); } catch { /* private browsing can reject storage */ }
}

export function resetSubscriptions(): RssSubscriptionState {
  const next = defaultRssSubscriptionState();
  try {
    storage()?.removeItem(RSS_SUBSCRIPTIONS_STORAGE_KEY);
    storage()?.removeItem(LEGACY_RSS_SUBSCRIPTIONS_STORAGE_KEY);
  } catch { /* ignore unavailable storage */ }
  return next;
}

export function orderRssSources(sources: RssSource[], state: RssSubscriptionState): RssSource[] {
  const byId = new Map(sources.map((source) => [source.id, source]));
  const trashed = new Set(state.trash.map((entry) => entry.id));
  const sourceOrder = [...state.order, ...sources.map((source) => source.id)]
    .filter((id, index, all) => all.indexOf(id) === index && byId.has(id) && !trashed.has(id));
  const pinned = new Set(state.pinned);
  return sourceOrder.sort((a, b) => Number(pinned.has(b)) - Number(pinned.has(a))).map((id) => byId.get(id)!).filter(Boolean);
}

export function removeRssSourcesById<T extends Pick<RssSource, "id">>(sources: T[], sourceIds: string[]): T[] {
  const removedIds = new Set(sourceIds);
  return sources.filter((source) => !removedIds.has(source.id));
}

export function trashSubscriptions(state: RssSubscriptionState, sourceIds: string[]): RssSubscriptionState {
  const order = uniqueStrings(state.order);
  const pinned = uniqueStrings(state.pinned);
  const custom = uniqueCustomSubscriptions(state.custom);
  const existingTrash = normalizeTrashEntries(state.trash) ?? [];
  const existingTrashIds = new Set(existingTrash.map((entry) => entry.id));
  const requestedIds = uniqueStrings(sourceIds).filter((id) => !existingTrashIds.has(id));
  const customById = new Map(custom.map((source) => [source.id, source]));
  const activeIds = new Set([...order, ...pinned, ...custom.map((source) => source.id)]);
  const entries = requestedIds.filter((id) => activeIds.has(id)).map((id): RssTrashEntry => {
    const customSource = customById.get(id);
    const positionInOrder = order.indexOf(id);
    return {
      id,
      kind: customSource ? "custom" : "builtin",
      previousIndex: Math.max(0, positionInOrder >= 0 ? positionInOrder : order.length),
      wasPinned: pinned.includes(id),
      ...(customSource ? { custom: { ...customSource } } : {}),
    };
  });
  const trashedIds = new Set([...existingTrashIds, ...entries.map((entry) => entry.id)]);
  const selectedIds = new Set(entries.map((entry) => entry.id));
  return {
    version: 2,
    order: order.filter((id) => !trashedIds.has(id)),
    pinned: pinned.filter((id) => !trashedIds.has(id)),
    custom: custom.filter((source) => !selectedIds.has(source.id) && !existingTrashIds.has(source.id)),
    trash: [...existingTrash, ...entries],
  };
}

export function restoreSubscriptions(state: RssSubscriptionState, sourceIds: string[]): RssSubscriptionState {
  const selectedIds = new Set(uniqueStrings(sourceIds));
  const trash = normalizeTrashEntries(state.trash) ?? [];
  const selectedTrashIds = new Set(trash.filter((entry) => selectedIds.has(entry.id)).map((entry) => entry.id));
  const order = uniqueStrings(state.order).filter((id) => !selectedTrashIds.has(id));
  const pinned = uniqueStrings(state.pinned).filter((id) => !selectedTrashIds.has(id));
  const custom = uniqueCustomSubscriptions(state.custom).filter((source) => !selectedTrashIds.has(source.id));

  const entriesToRestore = trash.filter((entry) => selectedTrashIds.has(entry.id)).sort((left, right) => left.previousIndex - right.previousIndex);
  for (const entry of entriesToRestore) {
    const insertAt = Math.max(0, Math.min(entry.previousIndex, order.length));
    if (!order.includes(entry.id)) order.splice(insertAt, 0, entry.id);
    if (entry.wasPinned && !pinned.includes(entry.id)) pinned.push(entry.id);
    if (entry.kind === "custom" && entry.custom && !custom.some((source) => source.id === entry.id)) custom.push({ ...entry.custom });
  }

  return {
    version: 2,
    order,
    pinned,
    custom,
    trash: trash.filter((entry) => !selectedTrashIds.has(entry.id)),
  };
}

export function restoreAllSubscriptions(state: RssSubscriptionState): RssSubscriptionState {
  return restoreSubscriptions(state, state.trash.map((entry) => entry.id));
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
  if (key === "hidden") return state.trash.some((entry) => entry.id === sourceId) ? restoreSubscriptions(state, [sourceId]) : trashSubscriptions(state, [sourceId]);
  const values = new Set(state.pinned);
  if (values.has(sourceId)) values.delete(sourceId); else values.add(sourceId);
  return { ...state, pinned: [...values] };
}

export function addCustomSubscription(state: RssSubscriptionState, source: Pick<CustomRssSubscription, "id" | "name" | "url">): RssSubscriptionState {
  const withoutExisting = state.trash.some((entry) => entry.id === source.id) ? restoreSubscriptions(state, [source.id]) : state;
  const custom = [...withoutExisting.custom.filter((item) => item.id !== source.id), source];
  return { ...withoutExisting, custom, order: [...withoutExisting.order.filter((id) => id !== source.id), source.id] };
}

export function removeCustomSource(state: RssSubscriptionState, sourceId: string): RssSubscriptionState {
  return trashSubscriptions(state, [sourceId]);
}
