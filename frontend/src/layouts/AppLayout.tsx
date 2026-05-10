import Sidebar from "../components/Sidebar";
import Topbar from "../components/Topbar";

export default function AppLayout({ children }: any) {
  return (
    <div className="flex h-screen bg-gray-950 text-white">
      <Sidebar />

      <div className="flex-1 flex flex-col">
        <Topbar />

        <div className="p-4 overflow-auto">{children}</div>
      </div>
    </div>
  );
}