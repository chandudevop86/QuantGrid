import Sidebar from "../components/Sidebar";
import Topbar from "../components/Topbar";

type AppLayoutProps = {
  children: React.ReactNode;
};

export default function AppLayout({ children }: AppLayoutProps) {
  return (
    <div className="app-shell">
      <Sidebar />

      <main className="app-main">
        <Topbar />

        <div className="app-content">{children}</div>
      </main>
    </div>
  );
}
