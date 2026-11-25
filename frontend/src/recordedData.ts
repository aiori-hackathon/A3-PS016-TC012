export async function loadRecordedData<T>(apiUrl: string, signal: AbortSignal) {
  const response = await fetch(apiUrl, { signal });
  if (!response.ok) throw new Error(`Backend request returned HTTP ${response.status}`);
  return { data: await response.json() as T, source: "api" as const };
}
