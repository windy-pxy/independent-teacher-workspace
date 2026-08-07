import { AppShell } from "@/components/app-shell";
import { ActionDialogProvider } from "@/components/action-dialog";

export default function WorkspaceLayout({ children }: { children: React.ReactNode }) {
  return <ActionDialogProvider><AppShell>{children}</AppShell></ActionDialogProvider>;
}
