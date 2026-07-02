// Display formatting for the demo dashboard.

export function formatScore(value: number): string {
  if (!Number.isFinite(value)) {
    throw new RangeError(`score must be finite, got ${value}`);
  }
  return value.toFixed(1);
}

export function formatItemCount(count: number): string {
  if (!Number.isInteger(count) || count < 0) {
    throw new RangeError(`item count must be a non-negative integer, got ${count}`);
  }
  return count === 1 ? "1 item" : `${count} items`;
}
