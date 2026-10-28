import { AuthProvider } from "@/components/auth";
import { AppShell } from "@/components/shell";

export default function AppLayout({ children }: LayoutProps<"/">) {
  return (
    <AuthProvider requireAuth>
      <AppShell>{children}</AppShell>
    </AuthProvider>
  );
}
