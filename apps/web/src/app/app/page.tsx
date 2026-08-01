import { AuthGate } from "@/components/auth/AuthGate";
import { Workspace } from "@/components/layout/Workspace";

export default function AppPage() {
  return (
    <AuthGate>
      <Workspace />
    </AuthGate>
  );
}
