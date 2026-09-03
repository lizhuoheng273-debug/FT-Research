from __future__ import annotations

import datetime as dt
import os


class LimitExceeded(RuntimeError):
    pass


class Limits:
    def __init__(self, store, guest_calls: int | None = None, ip_calls: int | None = None, site_calls: int | None = None):
        self.store = store
        self.guest_calls = guest_calls if guest_calls is not None else int(os.environ.get("FT_GUEST_DAILY_CALLS", "100"))
        self.ip_calls = ip_calls if ip_calls is not None else int(os.environ.get("FT_IP_DAILY_CALLS", "30"))
        self.site_calls = site_calls if site_calls is not None else int(os.environ.get("FT_SITE_DAILY_CALLS", "100"))

    def reserve(self, principal, ip: str, run_id: str | None = None) -> bool:
        bucket = dt.datetime.fromtimestamp(self.store.clock(), dt.timezone.utc).strftime("%Y-%m-%d")
        dimensions = [(f"principal:{principal.id}", self.guest_calls if principal.kind == "guest" else None),
                      (f"ip:{ip or 'unknown'}", self.ip_calls if principal.kind == "guest" else None),
                      ("site", self.site_calls if principal.kind == "guest" else None)]
        with self.store._connect() as conn:
            conn.execute("BEGIN IMMEDIATE")
            for dimension, limit in dimensions:
                if limit is None:
                    continue
                row = conn.execute("SELECT count FROM usage_counter WHERE bucket=? AND dimension=?", (bucket, dimension)).fetchone()
                if row and row["count"] >= limit:
                    raise LimitExceeded("体验额度已用尽，请稍后再试")
            for dimension, limit in dimensions:
                if limit is not None:
                    conn.execute("INSERT INTO usage_counter(bucket,dimension,count) VALUES(?,?,1) ON CONFLICT(bucket,dimension) DO UPDATE SET count=count+1", (bucket, dimension))
        return True
