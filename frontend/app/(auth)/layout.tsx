import { AuthProvider } from "@/components/auth";

export default function AuthLayout({ children }: LayoutProps<"/">) {
  return <AuthProvider requireAuth={false}>{children}</AuthProvider>;
}
