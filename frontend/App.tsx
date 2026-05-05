import Dashboard from "./pages/Dashboard";
import StrategyForm from "./components/StrategyForm";
import ExecutionForm from "./components/ExecutionForm";

function App() {
  return (
    <div className="flex h-screen bg-gray-950 text-white">

    {/* Sidebar */}
      <div className="w-64 bg-gray-900 p-5">
        <h2 className="text-2xl font-bold mb-6">🚀 QuantGrid</h2>

        <ul className="space-y-4">
          <li className="hover:text-blue-400 cursor-pointer">Dashboard</li>
          <li className="hover:text-blue-400 cursor-pointer">Strategies</li>
          <li className="hover:text-blue-400 cursor-pointer">Execution</li>
        </ul>
      </div>

      {/* Main Area */}
      <div className="flex-1 flex flex-col">

        {/* Topbar */}
        <div className="h-14 bg-gray-900 flex items-center justify-between px-6 border-b border-gray-800">
          <h1 className="text-lg font-semibold">Trading Dashboard</h1>
        </div>

        {/* Content */}
        <div className="p-6 grid grid-cols-2 gap-6">

          {/* Dashboard */}
          <div className="bg-gray-900 p-4 rounded-xl shadow">
            <Dashboard />
          </div>

          {/* Strategy */}
          <div className="bg-gray-900 p-4 rounded-xl shadow">
            <StrategyForm />
          </div>

          {/* Execution (full width) */}
          <div className="col-span-2 bg-gray-900 p-4 rounded-xl shadow">
            <ExecutionForm />
          </div>

        </div>
      </div>
    </div>
  );
}

export default App;