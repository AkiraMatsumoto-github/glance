// API の呼び出し。画面と API は同じオリジン（本番は FastAPI、開発は next dev の中継）。

export class ApiError extends Error {
  constructor(
    public status: number,
    public code: string,
    message: string,
  ) {
    super(message);
  }
}

type Options = {
  method?: "GET" | "POST" | "PUT" | "PATCH" | "DELETE";
  json?: unknown;
};

export async function api<T>(path: string, options: Options = {}): Promise<T> {
  const method = options.method ?? "GET";
  const headers: HeadersInit = {};
  let body: string | undefined;
  if (method !== "GET") {
    // 書き込みは JSON だけを受ける（サーバー側で確かめる）
    headers["content-type"] = "application/json";
    body = JSON.stringify(options.json ?? {});
  }
  const response = await fetch(path, { method, headers, body, credentials: "same-origin", cache: "no-store" });
  if (response.status === 204) {
    return undefined as T;
  }
  const data = await response.json().catch(() => ({}));
  if (response.status === 401) {
    // 未ログイン・許可切れはログイン画面へ（画面の外の関数なので、ページを読み直して移る）
    // 理由があれば、ログイン画面に出す（許可が切れた・許可リストから外れた）
    const reasons: Record<string, string> = { reauth_required: "reauth", not_allowed: "not_allowed" };
    const query = reasons[data.code] ? `?error=${reasons[data.code]}` : "";
    // eslint-disable-next-line @next/next/no-location-assign-relative-destination -- コンポーネントの外なので router が使えない
    window.location.href = `/login${query}`;
    throw new ApiError(401, data.code ?? "unauthenticated", data.message ?? "");
  }
  if (!response.ok) {
    throw new ApiError(response.status, data.code ?? "error", data.message || "エラーが起きました");
  }
  return data as T;
}

export function errorMessage(error: unknown): string {
  return error instanceof ApiError ? error.message : "通信できませんでした。時間をおいてもう一度試してください。";
}
