import { useEffect, useState } from "react";

function App() {
  const [strategies, setStrategies] = useState<string[]>([]);
  const [error, setError] = useState("");

  useEffect(() => {
    fetch("http://13.222.179.171:8000/trading/strategies")
      .then((res) => {
        if (!res.ok) throw new Error("API error");
        return res.json();
      })
      .then((data) => setStrategies(data))
      .catch((err) => {
        console.error(err);
        setError("Backend not reachable");
      });
  }, []);

  return (
    <div> style={{ padding: "20px", fontFamily: "Arial" }}
     <h1>🚀 QuantGrid Dashboard</h1>

      {error && <p style={{ color: "red" }}>{error}</p>}

      <h2>Available Strategies</h2>
      <ul>
        {strategies.map((s) => (
          <li key={s}>{s}</li>
        ))}
      </ul>
    </div>
  );
}

export default App;