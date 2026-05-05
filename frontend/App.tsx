import Dashboard from "./pages/Dashboard";
import StrategyForm from "./components/StrategyForm";
import ExecutionForm from "./components/ExecutionForm";

function App() {
  return (
    <div style={{ padding: 20 }}>
      <h1>🚀 QuantGrid</h1>

      <Dashboard />
      <StrategyForm />
      <ExecutionForm />
    </div>
  );
}

export default App;