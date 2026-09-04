import assert from "node:assert/strict";
import test from "node:test";

import { buildFeaturedEventCard } from "../src/lib/featuredEventCard.ts";

test("featured event cards use two-digit ranking and prefer the selected item summary", () => {
  const card = buildFeaturedEventCard(
    { rank: 3, id: "topic-3", title: "热点标题", summary: "事件详情摘要" },
    { id: "topic-3", title: "资讯标题", summary: "精选资讯摘要" },
  );

  assert.deepEqual(card, {
    rankLabel: "03",
    title: "热点标题",
    summary: "精选资讯摘要",
  });
});

test("featured event cards fall back to the archived topic summary", () => {
  const card = buildFeaturedEventCard(
    { rank: 10, id: "topic-10", title: "热点标题", summary: "事件详情摘要" },
  );

  assert.equal(card.rankLabel, "10");
  assert.equal(card.summary, "事件详情摘要");
});
