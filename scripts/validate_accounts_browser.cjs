/* Real browser + real API + disposable PostgreSQL. No production data or paid AI. */
const { chromium, expect } = require("@playwright/test");
const path = require("node:path");
const fs = require("node:fs");

async function main() {
  const browser = await chromium.launch({ channel: process.env.E2E_BROWSER_CHANNEL || "msedge", headless: true });
  const errors = [];
  const context = await browser.newContext({ viewport: { width: 1280, height: 900 } });
  const page = await context.newPage();
  page.on("pageerror", error => errors.push(error.message));
  const base = "http://127.0.0.1:3101";
  const password = "fictional-browser-password";
  const screenshots = path.resolve("var/validation");
  fs.mkdirSync(screenshots, { recursive: true });
  async function login(target, name, pass = password) {
    await target.goto(base + "/login");
    await target.getByLabel("账户名", { exact: true }).fill(name);
    await target.getByLabel("密码", { exact: true }).fill(pass);
    await target.getByRole("button", { name: "登录", exact: true }).click();
    await expect(target.getByRole("navigation", { name: "主导航" })).toBeVisible();
  }
  try {
    await page.goto(base + "/login");
    await page.getByRole("link", { name: "创建教师账户" }).click();
    await expect(page.getByRole("button", { name: "注册教师账户" })).toBeVisible();
    await page.screenshot({ path: path.join(screenshots, "m2-register.png"), fullPage: true });
    await page.getByLabel(/账户名/).fill("fictional-browser-a");
    await page.getByLabel(/^密码/).fill(password);
    await page.getByLabel("再次输入密码").fill("fictional-incorrect-confirmation");
    await page.getByRole("checkbox", { name: /隐私说明/ }).check();
    await page.getByRole("button", { name: "注册教师账户" }).click();
    await expect(page.getByRole("alert").filter({ hasText: "两次密码不一致" })).toBeVisible();
    await page.getByLabel("再次输入密码").fill(password);
    await page.getByRole("button", { name: "注册教师账户" }).click();
    await expect(page.getByText("注册成功，请先保存恢复码")).toBeVisible();
    const recovery = await page.getByLabel("恢复码", { exact: true }).inputValue();
    await expect(page.getByRole("link", { name: "前往登录" })).toHaveCount(0);
    await page.getByRole("checkbox").check();
    await page.getByRole("link", { name: "前往登录" }).click();
    await login(page, "fictional-browser-a");
    await page.getByRole("link", { name: "学生档案", exact: true }).click();
    await expect(page.getByText("暂无学生", { exact: true })).toBeVisible();
    await page.screenshot({ path: path.join(screenshots, "m2-student-empty.png"), fullPage: true });
    await page.getByLabel("姓名或代号", { exact: true }).fill("虚构浏览器学生");
    await page.getByRole("button", { name: /保存学生|添加学生|创建学生/ }).click();
    await expect(page.getByRole("heading", { name: "虚构浏览器学生", exact: true })).toBeVisible();
    await page.getByRole("button", { name: "退出", exact: true }).click();
    await expect(page.getByRole("heading", { name: "登录工作台" })).toBeVisible();
    const fresh = await browser.newContext();
    const otherPage = await fresh.newPage();
    await login(otherPage, "fictional-browser-a");
    await otherPage.getByRole("link", { name: "学生档案", exact: true }).click();
    await expect(otherPage.getByRole("heading", { name: "虚构浏览器学生", exact: true })).toBeVisible();
    await page.getByRole("link", { name: "忘记密码？" }).click();
    await expect(page.getByRole("heading", { name: "找回账户", exact: true })).toBeVisible();
    await page.getByLabel("账户名", { exact: true }).fill("fictional-browser-a");
    await page.getByLabel("恢复码", { exact: true }).fill(recovery);
    await page.getByLabel(/^新密码/).fill("fictional-browser-new-password");
    await page.getByLabel("再次输入密码").fill("fictional-browser-new-password");
    await page.getByRole("button", { name: "重设密码" }).click();
    await expect(page.getByRole("link", { name: "使用新密码登录" })).toBeVisible();
    await otherPage.reload();
    await expect(otherPage.getByRole("heading", { name: "登录工作台" })).toBeVisible();
    await login(page, "fictional-browser-a", "fictional-browser-new-password");
    await page.getByRole("link", { name: "账户安全", exact: true }).click();
    await expect(page.getByText("有效登录会话", { exact: true })).toBeVisible();
    await page.screenshot({ path: path.join(screenshots, "m2-account.png"), fullPage: true });
    await page.getByLabel("验证当前密码", { exact: true }).fill("fictional-browser-new-password");
    await page.getByRole("button", { name: "生成新的恢复码", exact: true }).click();
    await expect(page.getByLabel("请立即保存新恢复码", { exact: true })).toBeVisible();
    await expect(page.getByRole("button", { name: "生成新的恢复码", exact: true })).toBeDisabled();
    await page.getByRole("checkbox", { name: "我已安全保存新恢复码", exact: true }).check();
    await expect(page.getByRole("button", { name: "生成新的恢复码", exact: true })).toBeEnabled();
    await page.reload();
    await expect(page.getByText("有效登录会话", { exact: true })).toBeVisible();
    await expect(page.getByLabel("请立即保存新恢复码", { exact: true })).toHaveCount(0);
    await fresh.close();
    expect(errors).toEqual([]);
    console.log("PASS: first-user registration/error/recovery flow, student saved across fresh browser context; real API/PostgreSQL; browser errors 0");
  } catch (error) {
    await page.screenshot({ path: path.join(screenshots, "m2-failure.png"), fullPage: true });
    console.error(await page.locator("input").evaluateAll(inputs => inputs.map(input => ({ name: input.name, length: input.value.length, validation: input.validationMessage }))));
    throw error;
  } finally {
    await browser.close();
  }
}
main().catch(error => { console.error(error.message); process.exitCode = 1; });
