export type QueryValue = string | number | boolean | null | undefined;

/**
 * Build a query string without serializing missing values as "undefined".
 * Keeps links stable and avoids sending placeholder filter values to the API.
 */
export function queryString(values: Record<string, QueryValue>): string {
  const params = new URLSearchParams();
  for (const [key, value] of Object.entries(values)) {
    if (value === undefined || value === null || value === "") continue;
    params.set(key, String(value));
  }
  const result = params.toString();
  return result ? `?${result}` : "";
}
