/* Real Edge + real API + disposable PostgreSQL. Only fictional data; no paid AI. */
const { chromium, expect } = require("@playwright/test");
const fs = require("node:fs");
const path = require("node:path");

const base = "http://127.0.0.1:3102";
const password = "fictional-multitenant-browser-password";
const validationDir = path.resolve("var/validation");
const stateA = path.join(validationDir, "m3-owner-a-state.json");
const stateB = path.join(validationDir, "m3-owner-b-state.json");

async function register(page, username) {
  await page.goto(base + "/register");
  await expect(page.getByRole("button", { name: "注册教师账户" })).toBeVisible();
  await page.getByLabel(/账户名/).fill(username);
  await page.getByLabel(/^密码/).fill(password);
  await page.getByLabel("再次输入密码").fill(password);
  await page.getByRole("checkbox", { name: /隐私说明/ }).check();
  await page.getByRole("button", { name: "注册教师账户" }).click();
  await expect(page.getByText("注册成功，请先保存恢复码")).toBeVisible();
  await page.getByRole("checkbox").check();
  await page.getByRole("link", { name: "前往登录" }).click();
}

async function login(page, username) {
  await page.goto(base + "/login");
  await page.getByLabel("账户名", { exact: true }).fill(username);
  await page.getByLabel("密码", { exact: true }).fill(password);
  await page.getByRole("button", { name: "登录", exact: true }).click();
  await expect(page.getByRole("navigation", { name: "主导航" })).toBeVisible();
}

async function openStudents(page) {
  await page.getByRole("link", { name: "学生档案", exact: true }).click();
  await expect(page.getByRole("heading", { name: "学生档案", exact: true })).toBeVisible();
}

async function setup(browser, errors) {
  const contextA = await browser.newContext();
  const contextB = await browser.newContext();
  const pageA = await contextA.newPage();
  const pageB = await contextB.newPage();
  pageA.on("pageerror", error => errors.push(`A: ${error.message}`));
  pageB.on("pageerror", error => errors.push(`B: ${error.message}`));
  await register(pageA, "fictional-browser-owner-a");
  await login(pageA, "fictional-browser-owner-a");
  await openStudents(pageA);
  await expect(pageA.getByText("暂无学生", { exact: true })).toBeVisible();
  await pageA.getByLabel("姓名或代号", { exact: true }).fill("A浏览器专属虚构学生");
  await pageA.getByRole("button", { name: "创建学生" }).click();
  await expect(pageA.getByRole("heading", { name: "A浏览器专属虚构学生" })).toBeVisible();

  await register(pageB, "fictional-browser-owner-b");
  await login(pageB, "fictional-browser-owner-b");
  await openStudents(pageB);
  await expect(pageB.getByText("暂无学生", { exact: true })).toBeVisible();
  await expect(pageB.getByText("A浏览器专属虚构学生")).toHaveCount(0);
  await pageB.getByLabel("姓名或代号", { exact: true }).fill("B浏览器专属虚构学生");
  await pageB.getByRole("button", { name: "创建学生" }).click();
  await expect(pageB.getByRole("heading", { name: "B浏览器专属虚构学生" })).toBeVisible();
  await contextA.storageState({ path: stateA });
  await contextB.storageState({ path: stateB });
  await contextA.close();
  await contextB.close();
}

async function persistenceAndTabs(browser, errors) {
  const contextA = await browser.newContext({ storageState: stateA });
  const contextB = await browser.newContext({ storageState: stateB });
  const pageA = await contextA.newPage();
  const pageB = await contextB.newPage();
  pageA.on("pageerror", error => errors.push(`A restart: ${error.message}`));
  pageB.on("pageerror", error => errors.push(`B restart: ${error.message}`));
  await pageA.goto(base + "/students");
  await pageB.goto(base + "/students");
  await expect(pageA.getByRole("heading", { name: "A浏览器专属虚构学生" })).toBeVisible();
  await expect(pageA.getByText("B浏览器专属虚构学生")).toHaveCount(0);
  await expect(pageB.getByRole("heading", { name: "B浏览器专属虚构学生" })).toBeVisible();
  await expect(pageB.getByText("A浏览器专属虚构学生")).toHaveCount(0);

  await pageB.getByLabel("姓名或代号", { exact: true }).fill("尚未保存的虚构学生");
  await pageB.getByRole("link", { name: "课程与课表", exact: true }).click();
  await expect(pageB.getByRole("alert").filter({ hasText: "还没有保存" })).toBeVisible();
  await pageB.getByRole("button", { name: "留在本页" }).click();
  await expect(pageB.getByLabel("姓名或代号", { exact: true })).toHaveValue("尚未保存的虚构学生");
  await pageB.getByLabel("姓名或代号", { exact: true }).fill("");

  // A first-time teacher can discover the disabled AI state, export data,
  // understand a deletion mistake, then schedule and cancel without developer help.
  await pageB.getByRole("link", { name: "模板与 AI", exact: true }).click();
  await expect(pageB.getByText(/当前账户尚未开通 AI 生成额度/)).toBeVisible();
  await pageB.getByRole("link", { name: "账户安全", exact: true }).click();
  const downloadPromise = pageB.waitForEvent("download");
  await pageB.getByRole("button", { name: "导出我的全部资料" }).click();
  const download = await downloadPromise;
  expect(download.suggestedFilename()).toMatch(/\.zip$/);
  const deletionSection = pageB.getByRole("heading", { name: "删除账户与全部资料" })
    .locator("..");
  await deletionSection.getByLabel(/输入账户名/).fill("wrong-account-name");
  await deletionSection.getByLabel("验证当前密码").fill(password);
  await deletionSection.getByRole("button", { name: "申请删除账户" }).click();
  await expect(pageB.getByRole("alert").filter({ hasText: "确认账户名不一致" })).toBeVisible();
  await deletionSection.getByLabel(/输入账户名/).fill("fictional-browser-owner-b");
  await deletionSection.getByRole("button", { name: "申请删除账户" }).click();
  await expect(pageB.getByText(/账户删除申请已提交/)).toBeVisible();
  await pageB.getByRole("button", { name: "取消删除，继续保留账户" }).click();
  await expect(pageB.getByText(/账户删除申请已取消/)).toBeVisible();
  await pageB.getByRole("link", { name: "学生档案", exact: true }).click();
  await expect(pageB.getByRole("heading", { name: "B浏览器专属虚构学生" })).toBeVisible();

  const concurrent = await browser.newContext({ storageState: stateA });
  const concurrentPage = await concurrent.newPage();
  concurrentPage.on("pageerror", error => errors.push(`concurrent: ${error.message}`));
  await concurrentPage.goto(base + "/students");
  await concurrentPage.getByRole("button", { name: "编辑资料" }).click();
  await pageA.getByRole("button", { name: "编辑资料" }).click();
  await pageA.getByRole("dialog").getByLabel("学生姓名或代号").fill("A浏览器专属虚构学生已更新");
  await pageA.getByRole("dialog").getByRole("button", { name: "保存修改" }).click();
  await expect(pageA.getByRole("heading", { name: "A浏览器专属虚构学生已更新" })).toBeVisible();
  await concurrentPage.getByRole("dialog").getByLabel("学生姓名或代号").fill("不应覆盖的并发修改");
  await concurrentPage.getByRole("dialog").getByRole("button", { name: "保存修改" }).click();
  await expect(
    concurrentPage.getByRole("alert").filter({ hasText: "记录已被其他操作更新" }),
  ).toBeVisible();
  await concurrent.close();

  const switcher = await contextA.newPage();
  switcher.on("pageerror", error => errors.push(`switcher: ${error.message}`));
  await switcher.goto(base + "/students");
  await switcher.getByRole("button", { name: "退出", exact: true }).click();
  await expect(
    pageA.getByRole("alert").filter({ hasText: "另一个标签页更改了登录状态" }),
  ).toBeVisible();
  await login(switcher, "fictional-browser-owner-b");

  const blocked = await pageA.evaluate(async () => {
    const csrfPart = document.cookie.split(";").map(value => value.trim())
      .find(value => value.startsWith("teacher_workspace_session_csrf="));
    const csrf = csrfPart ? decodeURIComponent(csrfPart.split("=").slice(1).join("=")) : "";
    const expected = sessionStorage.getItem("teacher-workspace:tab-user-id") || "";
    const response = await fetch("/api/v1/students", {
      method: "POST",
      credentials: "include",
      headers: {
        "Content-Type": "application/json",
        "Origin": location.origin,
        "X-CSRF-Token": csrf,
        "X-Expected-User-ID": expected,
      },
      body: JSON.stringify({ display_name: "不应串号保存的虚构学生" }),
    });
    return { status: response.status, body: await response.json() };
  });
  expect(blocked.status).toBe(409);
  expect(blocked.body.code).toBe("ACCOUNT_CONTEXT_CHANGED");
  await pageB.reload();
  await expect(pageB.getByText("不应串号保存的虚构学生")).toHaveCount(0);
  await contextA.close();
  await contextB.close();
}

async function main() {
  fs.mkdirSync(validationDir, { recursive: true });
  const browser = await chromium.launch({
    channel: process.env.E2E_BROWSER_CHANNEL || "msedge",
    headless: true,
  });
  const errors = [];
  try {
    if (process.argv.includes("--setup")) await setup(browser, errors);
    else await persistenceAndTabs(browser, errors);
    expect(errors).toEqual([]);
    console.log(process.argv.includes("--setup")
      ? "PASS: two novice teachers registered and saved isolated fictional students"
      : "PASS: persistence after restart, separate contexts, tab-switch blocking, errors 0");
  } finally {
    await browser.close();
  }
}

main().catch(error => { console.error(error); process.exitCode = 1; });
