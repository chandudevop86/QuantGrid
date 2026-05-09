import { useEffect, useState } from "react";
import { api } from "../api"; // adjust path if needed

export default function Strategies() {
  const [strategies, setStrategies] = useState([]);

  useEffect(() => {
    const loadStrategies = async () => {
      try {
        const data = await api.getStrategies();
        setStrategies(data);
      } catch (err) {
        console.error("Error loading strategies:", err);
      }
    };

    loadStrategies();
  }, []);

  return (
    <div>
      <h1>Strategies</h1>

      {strategies.map((s: any, i: number) => (
        <div key={i}>{s.name}</div>
      ))}
    </div>
  );
}