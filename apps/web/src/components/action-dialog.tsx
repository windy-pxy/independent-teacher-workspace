"use client";

import * as Dialog from "@radix-ui/react-dialog";
import { X } from "@phosphor-icons/react";
import { FormEvent, createContext, useCallback, useContext, useRef, useState } from "react";

export type ActionDialogField = {
  name: string;
  label: string;
  value?: string | null;
  type?: "text" | "textarea" | "number" | "datetime-local" | "select";
  placeholder?: string;
  helper?: string;
  required?: boolean;
  maxLength?: number;
  min?: number;
  max?: number;
  step?: number;
  options?: Array<{ label: string; value: string }>;
};

export type ActionDialogOptions = {
  title: string;
  description?: string;
  fields: ActionDialogField[];
  submitLabel?: string;
  tone?: "default" | "danger";
  width?: "compact" | "wide";
};

export type ActionDialogResult = Record<string, string> | null;

type PendingDialog = ActionDialogOptions & {
  resolve: (value: ActionDialogResult) => void;
};

const ActionDialogContext = createContext<
  ((options: ActionDialogOptions) => Promise<ActionDialogResult>) | null
>(null);

export function ActionDialogProvider({ children }: { children: React.ReactNode }) {
  const [pending, setPending] = useState<PendingDialog | null>(null);
  const settled = useRef(false);

  const openDialog = useCallback((options: ActionDialogOptions) => {
    return new Promise<ActionDialogResult>((resolve) => {
      settled.current = false;
      setPending({ ...options, resolve });
    });
  }, []);

  const finish = useCallback(
    (result: ActionDialogResult) => {
      if (!pending || settled.current) return;
      settled.current = true;
      pending.resolve(result);
      setPending(null);
    },
    [pending],
  );

  function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const data = new FormData(event.currentTarget);
    finish(Object.fromEntries(pending?.fields.map((field) => [field.name, String(data.get(field.name) ?? "")]) ?? []));
  }

  return (
    <ActionDialogContext.Provider value={openDialog}>
      {children}
      <Dialog.Root open={Boolean(pending)} onOpenChange={(open) => !open && finish(null)}>
        <Dialog.Portal>
          <Dialog.Overlay className="dialog-overlay" />
          <Dialog.Content
            className={`dialog-panel ${pending?.width === "wide" ? "dialog-panel-wide" : ""}`}
            onEscapeKeyDown={() => finish(null)}
          >
            {pending ? (
              <form onSubmit={submit}>
                <div className="dialog-header">
                  <div>
                    <Dialog.Title className="dialog-title">{pending.title}</Dialog.Title>
                    {pending.description ? (
                      <Dialog.Description className="dialog-description">
                        {pending.description}
                      </Dialog.Description>
                    ) : null}
                  </div>
                  <Dialog.Close asChild>
                    <button className="icon-button" type="button" aria-label="关闭编辑面板">
                      <X size={20} weight="regular" />
                    </button>
                  </Dialog.Close>
                </div>

                <div className="dialog-body">
                  {pending.fields.map((field) => {
                    const id = `dialog-field-${field.name}`;
                    const shared = {
                      id,
                      name: field.name,
                      defaultValue: field.value ?? "",
                      placeholder: field.placeholder,
                      required: field.required,
                      maxLength: field.maxLength,
                    };
                    return (
                      <label className="dialog-field" key={field.name} htmlFor={id}>
                        <span className="dialog-field-label">
                          {field.label}
                          {field.required ? <span aria-hidden="true"> *</span> : null}
                        </span>
                        {field.type === "textarea" ? (
                          <textarea className="field min-h-24 resize-y" {...shared} />
                        ) : field.type === "select" ? (
                          <select className="field" {...shared}>
                            {field.options?.map((option) => (
                              <option key={option.value} value={option.value}>
                                {option.label}
                              </option>
                            ))}
                          </select>
                        ) : (
                          <input
                            className="field"
                            type={field.type ?? "text"}
                            min={field.min}
                            max={field.max}
                            step={field.step}
                            {...shared}
                          />
                        )}
                        {field.helper ? <span className="dialog-field-helper">{field.helper}</span> : null}
                      </label>
                    );
                  })}
                </div>

                <div className="dialog-footer">
                  <Dialog.Close asChild>
                    <button className="button-secondary" type="button">取消</button>
                  </Dialog.Close>
                  <button
                    className={pending.tone === "danger" ? "button-danger-solid" : "button-primary"}
                    type="submit"
                  >
                    {pending.submitLabel ?? "保存修改"}
                  </button>
                </div>
              </form>
            ) : null}
          </Dialog.Content>
        </Dialog.Portal>
      </Dialog.Root>
    </ActionDialogContext.Provider>
  );
}

export function useActionDialog() {
  const context = useContext(ActionDialogContext);
  if (!context) throw new Error("useActionDialog 必须在 ActionDialogProvider 内使用");
  return context;
}
