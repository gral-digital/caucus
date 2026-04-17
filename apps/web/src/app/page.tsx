import { ChatView } from "@/components/chat/ChatView";
import { Sidebar } from "@/components/layout/Sidebar";

export default function Home() {
  return (
    <div className="flex h-screen w-screen overflow-hidden">
      <Sidebar />
      <main className="flex h-full flex-1 flex-col bg-paper">
        <ChatView />
      </main>
    </div>
  );
}
