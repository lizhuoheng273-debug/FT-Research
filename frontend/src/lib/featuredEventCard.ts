interface FeaturedTopic {
  rank: number;
  title: string;
  summary?: string;
}

interface FeaturedItem {
  summary?: string;
}

export function buildFeaturedEventCard(topic: FeaturedTopic, item?: FeaturedItem) {
  return {
    rankLabel: String(topic.rank).padStart(2, "0"),
    title: topic.title,
    summary: item?.summary?.trim() || topic.summary?.trim() || "",
  };
}
