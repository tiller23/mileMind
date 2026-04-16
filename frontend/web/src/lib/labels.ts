import type { InjuryTag } from "./types";

export const INJURY_TAG_LABEL: Record<InjuryTag, string> = {
  knee: "Knee",
  it_band: "IT Band",
  plantar_fasciitis: "Plantar Fasciitis",
  achilles: "Achilles",
  hip: "Hip",
  lower_back: "Lower Back",
  hamstring: "Hamstring",
  shin_splints: "Shin Splints",
};

export function injuryTagLabel(tag: string): string {
  return INJURY_TAG_LABEL[tag as InjuryTag] ?? tag;
}
