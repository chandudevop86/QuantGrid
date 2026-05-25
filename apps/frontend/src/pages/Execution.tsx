import ExecutionForm from "../components/ExecutionForm";

export default function Execution() {
  return (
    <section className="dashboard-page">
      <div className="page-heading">
        <h1>Execution</h1>
        <p>Submit a paper execution order to the trading API.</p>
      </div>
      <ExecutionForm />
    </section>
  );
}
