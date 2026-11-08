/** Index of the last segment whose start is at or before `t` (binary search); -1 before the first. */
export function findActiveSegment(segments: { start_sec: number }[], t: number): number {
  let lo = 0;
  let hi = segments.length - 1;
  let ans = -1;
  while (lo <= hi) {
    const mid = (lo + hi) >> 1;
    if (segments[mid].start_sec <= t) {
      ans = mid;
      lo = mid + 1;
    } else {
      hi = mid - 1;
    }
  }
  return ans;
}

/** Case-insensitive substring matches inside each segment's text. */
export function filterSegments(
  segments: { text: string }[],
  query: string,
): { index: number; ranges: [number, number][] }[] {
  const q = query.trim().toLowerCase();
  if (!q) return [];
  const out: { index: number; ranges: [number, number][] }[] = [];
  segments.forEach((s, index) => {
    const text = s.text.toLowerCase();
    const ranges: [number, number][] = [];
    let from = 0;
    for (;;) {
      const i = text.indexOf(q, from);
      if (i < 0) break;
      ranges.push([i, i + q.length]);
      from = i + q.length;
    }
    if (ranges.length) out.push({ index, ranges });
  });
  return out;
}
