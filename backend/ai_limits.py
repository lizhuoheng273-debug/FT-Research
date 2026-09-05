from __future__ import annotations

import datetime as dt
import os


class LimitExceeded(RuntimeError):
    pass


class Limits:
    def __init__(
        self,
        store,
        guest_calls: int | None = None,
        ip_calls: int | None = None,
        site_calls: int | None = None,
        guest_questions: int | None = None,
        guest_session_ip: int | None = None,
        guest_session_site: int | None = None,
    ):
        self.store = store
        self.guest_calls = guest_calls if guest_calls is not None else int(os.environ.get("FT_GUEST_DAILY_CALLS", "100"))
        self.ip_calls = ip_calls if ip_calls is not None else int(os.environ.get("FT_IP_DAILY_CALLS", "30"))
        self.site_calls = site_calls if site_calls is not None else int(os.environ.get("FT_SITE_DAILY_CALLS", "100"))
        self.guest_questions = guest_questions if guest_questions is not None else int(os.environ.get("FT_GUEST_DAILY_QUESTIONS", "5"))
        self.guest_session_ip = guest_session_ip if guest_session_ip is not None else int(os.environ.get("FT_GUEST_SESSION_IP_PER_HOUR", "20"))
        self.guest_session_site = guest_session_site if guest_session_site is not None else int(os.environ.get("FT_GUEST_SESSION_SITE_PER_HOUR", "200"))

    def reserve_guest_session(self, ip: str) -> bool:
        now = dt.datetime.fromtimestamp(self.store.clock(), dt.timezone.utc)
        bucket = now.strftime("%Y-%m-%dT%H")
        stale_before = (now - dt.timedelta(days=7)).strftime("%Y-%m-%d")
        dimensions = ((f"guest-session-ip:{ip or 'unknown'}", self.guest_session_ip),
                      ("guest-session-site", self.guest_session_site))
        with self.store._connect() as conn:
            conn.execute("BEGIN IMMEDIATE")
            conn.execute("DELETE FROM usage_counter WHERE bucket < ?", (stale_before,))
            for dimension, limit in dimensions:
                row = conn.execute("SELECT count FROM usage_counter WHERE bucket=? AND dimension=?", (bucket, dimension)).fetchone()
                if row and row["count"] >= limit:
                    raise LimitExceeded("访客会话创建过于频繁，请稍后再试")
            for dimension, _limit in dimensions:
                conn.execute("INSERT INTO usage_counter(bucket,dimension,count) VALUES(?,?,1) ON CONFLICT(bucket,dimension) DO UPDATE SET count=count+1", (bucket, dimension))
        return True

    def reserve_question(self, principal) -> bool:
        if principal.kind != "guest":
            return True
        bucket = __import__("datetime").datetime.fromtimestamp(self.store.clock(), __import__("datetime").timezone.utc).strftime("%Y-%m-%d")
        dimension = f"questions:{principal.id}"
        with self.store._connect() as conn:
            conn.execute("BEGIN IMMEDIATE")
            row = conn.execute("SELECT count FROM usage_counter WHERE bucket=? AND dimension=?", (bucket, dimension)).fetchone()
            if row and row["count"] >= self.guest_questions:
                raise LimitExceeded("本次访客体验的提问额度已用尽")
            conn.execute("INSERT INTO usage_counter(bucket,dimension,count) VALUES(?,?,1) ON CONFLICT(bucket,dimension) DO UPDATE SET count=count+1", (bucket, dimension))
        return True

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
