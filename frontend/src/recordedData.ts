type RecordedData<T> = { data: T; source: "api" | "recorded" };

async function readJson<T>(url: string, signal: AbortSignal): Promise<T> {
  const response = await fetch(url, { signal });
  if (!response.ok) throw new Error(`Data request returned HTTP ${response.status}`);
  return response.json() as Promise<T>;
}

export async function loadRecordedData<T>(
  recordedUrl: string,
  signal: AbortSignal,
  apiUrl?: string,
): Promise<RecordedData<T>> {
  if (apiUrl) {
    try {
      return { data: await readJson<T>(apiUrl, signal), source: "api" };
    } catch (error) {
      if (signal.aborted) throw error;
    }
  }

  return { data: await readJson<T>(recordedUrl, signal), source: "recorded" };
}
