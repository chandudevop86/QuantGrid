const timestampKeys = new Set([
  "created_at",
  "queued_at",
  "updated_at",
  "worker_started_at",
  "completed_at",
  "signal_time",
  "timestamp",
  "latest_candle_at",
  "server_time",
]);

function isIsoTimestamp(value: unknown) {
  return typeof value === "string" && /^\d{4}-\d{2}-\d{2}T/.test(value);
}

export function formatLocalDateTime(value?: string | null) {
  if (!value) return "-";

  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;

  return new Intl.DateTimeFormat(undefined, {
    year: "numeric",
    month: "short",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
    timeZoneName: "short",
  }).format(date);
}

export function localizeTimestamps(value: unknown): unknown {
  if (Array.isArray(value)) {
    return value.map((item) => localizeTimestamps(item));
  }

  if (!value || typeof value !== "object") {
    return value;
  }

  return Object.fromEntries(
    Object.entries(value).map(([key, item]) => {
      if (timestampKeys.has(key) && isIsoTimestamp(item)) {
        return [key, formatLocalDateTime(item)];
      }

      return [key, localizeTimestamps(item)];
    })
  );
}
