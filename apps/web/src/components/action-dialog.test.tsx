import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { useState } from "react";
import { afterEach, describe, expect, it } from "vitest";

import { ActionDialogProvider, useActionDialog } from "./action-dialog";

afterEach(cleanup);

function Harness() {
  const openDialog = useActionDialog();
  const [result, setResult] = useState("尚未保存");
  return (
    <>
      <button
        type="button"
        onClick={async () => {
          const values = await openDialog({
            title: "编辑学生资料",
            fields: [{ name: "display_name", label: "学生姓名或代号", value: "虚构学生", required: true }],
          });
          if (values) setResult(values.display_name);
        }}
      >
        编辑
      </button>
      <output>{result}</output>
    </>
  );
}

describe("ActionDialogProvider", () => {
  it("在站内完成编辑并返回表单值", async () => {
    render(<ActionDialogProvider><Harness /></ActionDialogProvider>);

    fireEvent.click(screen.getByRole("button", { name: "编辑" }));
    expect(screen.getByRole("dialog", { name: "编辑学生资料" })).toBeInTheDocument();

    const input = screen.getByLabelText(/学生姓名或代号/);
    fireEvent.change(input, { target: { value: "虚构学生甲" } });
    fireEvent.click(screen.getByRole("button", { name: "保存修改" }));

    await waitFor(() => expect(screen.getByText("虚构学生甲")).toBeInTheDocument());
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
  });

  it("取消时不会修改调用方状态", async () => {
    render(<ActionDialogProvider><Harness /></ActionDialogProvider>);
    fireEvent.click(screen.getByRole("button", { name: "编辑" }));
    fireEvent.click(screen.getByRole("button", { name: "取消" }));
    await waitFor(() => expect(screen.queryByRole("dialog")).not.toBeInTheDocument());
    expect(screen.getByText("尚未保存")).toBeInTheDocument();
  });
});
