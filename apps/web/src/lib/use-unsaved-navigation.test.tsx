import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";

import { useUnsavedNavigation } from "./use-unsaved-navigation";

function Harness({ dirty }: { dirty: boolean }) {
  const warning = useUnsavedNavigation(dirty);
  return (
    <>
      <a href="/lessons">前往课程</a>
      {warning.pendingHref ? <p role="alert">资料未保存</p> : null}
      <button onClick={warning.stay}>留下</button>
    </>
  );
}

afterEach(cleanup);

describe("不了解网站的教师离开未保存表单", () => {
  it("拦截站内导航并允许继续填写", () => {
    render(<Harness dirty />);
    fireEvent.click(screen.getByRole("link", { name: "前往课程" }));
    expect(screen.getByRole("alert")).toHaveTextContent("资料未保存");
    fireEvent.click(screen.getByRole("button", { name: "留下" }));
    expect(screen.queryByRole("alert")).not.toBeInTheDocument();
  });

  it("空白表单不拦截导航", () => {
    render(<Harness dirty={false} />);
    expect(screen.queryByRole("alert")).not.toBeInTheDocument();
  });
});
