import { useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { api } from "../api";
import { roles, setCurrentAuth, type Role } from "../roles";

export default function Signup() {
  const navigate = useNavigate();
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [confirmation, setConfirmation] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);
  const submit = async (event: React.FormEvent) => {
    event.preventDefault(); setError(null);
    if (password !== confirmation) { setError("Passwords do not match."); return; }
    setSubmitting(true);
    try {
      const response = await api.register({ username: username.trim(), password });
      if (!response?.access_token || !roles.includes(response.role as Role)) throw new Error("Registration response is invalid.");
      setCurrentAuth(response.role as Role, response.access_token);
      navigate("/subscription", { replace: true });
    } catch (caught: any) {
      const detail = caught?.response?.data?.detail;
      setError(typeof detail === "string" ? detail : caught?.message ?? "Account creation failed.");
    } finally { setSubmitting(false); }
  };
  return <section className="qg-signup-page"><article className="qg-card qg-signup-card">
    <span className="qg-card-label">Create your account</span><h1>Start with QuantGrid Free.</h1>
    <p>Use delayed decision support and paper trading first. Paid access is activated separately.</p>
    <form onSubmit={submit}>
      <label>Username<input autoComplete="username" required maxLength={80} value={username} onChange={(event) => setUsername(event.target.value)} /></label>
      <label>Password<input autoComplete="new-password" required type="password" value={password} onChange={(event) => setPassword(event.target.value)} /></label>
      <label>Confirm password<input autoComplete="new-password" required type="password" value={confirmation} onChange={(event) => setConfirmation(event.target.value)} /></label>
      <small>Use at least 10 characters with upper and lower case letters, a number, and a symbol.</small>
      {error && <div className="alert alert-error" role="alert">{error}</div>}
      <button type="submit" disabled={submitting}>{submitting ? "Creating account…" : "Create free account"}</button>
    </form>
    <footer>Already registered? <Link to="/">Sign in</Link> · <Link to="/plans">Compare plans</Link></footer>
  </article></section>;
}
