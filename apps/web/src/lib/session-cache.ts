import type { QueryClient } from "@tanstack/react-query";

/** Cancel old requests before clearing account-scoped data. */
export async function clearSessionCache(client: QueryClient): Promise<void> {
  await client.cancelQueries();
  client.clear();
}
