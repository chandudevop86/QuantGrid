export default function Topbar() {
  return (
    <header style={{ height: 56, display: "flex", alignItems: "center", justifyContent: "space-between", padding: "0 24px", borderBottom: "1px solid #1e293b", background: "#0f172a" }}>
      <strong>QuantGrid</strong>
      <span style={{ color: "#94a3b8", fontSize: 14 }}>Trading Control Center</span>
    </header>
  );
}
