import { QueryClient } from "@tanstack/react-query";
import { describe, expect, it } from "vitest";

import { clearSessionCache } from "./session-cache";

describe("账户切换缓存隔离", () => {
  it("清除上一教师资料与会话缓存，下一教师相同查询只得到自己的记录", async () => {
    const client = new QueryClient();
    client.setQueryData(["auth", "me"], { username: "fictional-teacher-a" });
    client.setQueryData(["students"], [{ display_name: "虚构甲的学生" }]);
    await clearSessionCache(client);
    expect(client.getQueryData(["auth", "me"])).toBeUndefined();
    expect(client.getQueryData(["students"])).toBeUndefined();
    const result = await client.fetchQuery({
      queryKey: ["students"],
      queryFn: async () => [{ display_name: "虚构乙的学生" }],
    });
    expect(result).toEqual([{ display_name: "虚构乙的学生" }]);
    client.clear();
  });

  it("退出时取消尚未完成的请求，迟到的结果不会重新填入旧资料", async () => {
    const client = new QueryClient();
    let finish!: (value: string[]) => void;
    const request = client.fetchQuery({
      queryKey: ["students"],
      queryFn: () => new Promise<string[]>((resolve) => { finish = resolve; }),
    }).catch(() => undefined);
    await clearSessionCache(client);
    finish(["虚构甲的学生"]);
    await request;
    expect(client.getQueryData(["students"])).toBeUndefined();
    expect(client.getQueryCache().getAll()).toHaveLength(0);
  });
});
