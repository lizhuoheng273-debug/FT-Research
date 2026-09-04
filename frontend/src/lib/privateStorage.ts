export interface PrivateIdentity { id: string; kind: 'owner' | 'guest' }

export interface StorageLike {
  getItem(key: string): string | null;
  setItem(key: string, value: string): void;
  removeItem(key: string): void;
}

const OWNER_PREFIX = 'ft:owner:';

export function createPrivateStorage(identity: PrivateIdentity, ownerStorage?: StorageLike) {
  const memory = new Map<string, string>();
  const disk = ownerStorage ?? (typeof localStorage === 'undefined' ? undefined : localStorage);
  const ownerKey = (key: string) => `${OWNER_PREFIX}${key}`;
  return {
    get(key: string): string | null {
      if (identity.kind === 'guest') return memory.get(key) ?? null;
      try { return disk?.getItem(ownerKey(key)) ?? null; } catch { return null; }
    },
    set(key: string, value: string): void {
      if (identity.kind === 'guest') { memory.set(key, value); return; }
      try { disk?.setItem(ownerKey(key), value); } catch { /* private mode */ }
    },
    remove(key: string): void {
      if (identity.kind === 'guest') { memory.delete(key); return; }
      try { disk?.removeItem(ownerKey(key)); } catch { /* private mode */ }
    },
    clearMemory(): void { memory.clear(); },
  };
}
