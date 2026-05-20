import { useEffect, useState } from "react";
import { api } from "../api";
import { getCurrentUserId, roleLabels, roles, type Role } from "../roles";

type User = {
  id: number;
  username: string;
  role: Role;
};

export default function AdminUsers() {
  const [users, setUsers] = useState<User[]>([]);
  const [message, setMessage] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [role, setRole] = useState<Role>("viewer");
  const [resetPassword, setResetPassword] = useState("");
  const [ownOldPassword, setOwnOldPassword] = useState("");
  const [ownNewPassword, setOwnNewPassword] = useState("");
  const currentUserId = getCurrentUserId();

  const loadUsers = () =>
    api
      .listUsers()
      .then(setUsers)
      .catch((err: any) => setError(err?.response?.data?.detail ?? "Unable to load users."));

  useEffect(() => {
    void loadUsers();
  }, []);

  const clearStatus = () => {
    setMessage(null);
    setError(null);
  };

  const createUser = async (event: React.FormEvent) => {
    event.preventDefault();
    clearStatus();
    try {
      await api.createUser({ username, password, role });
      setMessage(`Created ${username}.`);
      setUsername("");
      setPassword("");
      setRole("viewer");
      await loadUsers();
    } catch (err: any) {
      setError(err?.response?.data?.detail ?? "Create user failed.");
    }
  };

  const resetUserPassword = async (userId: number) => {
    clearStatus();
    try {
      await api.resetUserPassword(userId, resetPassword);
      setMessage("Password reset.");
      setResetPassword("");
    } catch (err: any) {
      setError(err?.response?.data?.detail ?? "Password reset failed.");
    }
  };

  const deleteUser = async (userId: number) => {
    clearStatus();
    try {
      await api.deleteUser(userId);
      setMessage("User deleted.");
      await loadUsers();
    } catch (err: any) {
      setError(err?.response?.data?.detail ?? "Delete user failed.");
    }
  };

  const changeOwnPassword = async (event: React.FormEvent) => {
    event.preventDefault();
    if (!currentUserId) return;
    clearStatus();
    try {
      await api.changeUserPassword(currentUserId, ownOldPassword, ownNewPassword);
      setMessage("Password changed.");
      setOwnOldPassword("");
      setOwnNewPassword("");
    } catch (err: any) {
      setError(err?.response?.data?.detail ?? "Password change failed.");
    }
  };

  return (
    <section className="dashboard-page">
      <div className="page-heading">
        <h1>User Management</h1>
        <p>Create users, reset passwords, delete accounts, and change your password.</p>
      </div>

      {message && <div className="alert alert-success">{message}</div>}
      {error && <div className="alert alert-error">{error}</div>}

      <div className="strategy-layout">
        <form className="form-panel" onSubmit={createUser}>
          <div className="form-panel-header">
            <div>
              <h2>Create User</h2>
              <p>Password must be 10+ chars with upper/lowercase, number, and special char.</p>
            </div>
          </div>
          <input value={username} onChange={(event) => setUsername(event.target.value)} placeholder="Username" />
          <input value={password} onChange={(event) => setPassword(event.target.value)} placeholder="Password" type="password" />
          <select value={role} onChange={(event) => setRole(event.target.value as Role)}>
            {roles.map((item) => (
              <option key={item} value={item}>
                {roleLabels[item]}
              </option>
            ))}
          </select>
          <button className="primary-action" type="submit">Create User</button>
        </form>

        <form className="form-panel" onSubmit={changeOwnPassword}>
          <div className="form-panel-header">
            <div>
              <h2>Change My Password</h2>
              <p>Use your current password to rotate your own credentials.</p>
            </div>
          </div>
          <input value={ownOldPassword} onChange={(event) => setOwnOldPassword(event.target.value)} placeholder="Current password" type="password" />
          <input value={ownNewPassword} onChange={(event) => setOwnNewPassword(event.target.value)} placeholder="New password" type="password" />
          <button className="primary-action" type="submit">Change Password</button>
        </form>
      </div>

      <div className="dashboard-section">
        <div className="section-header">
          <h2>Users</h2>
          <span>{users.length} total</span>
        </div>
        <div className="table-wrap">
          <table className="table">
            <thead>
              <tr>
                <th>ID</th>
                <th>Username</th>
                <th>Role</th>
                <th>Reset Password</th>
                <th>Delete</th>
              </tr>
            </thead>
            <tbody>
              {users.map((user) => (
                <tr key={user.id}>
                  <td>{user.id}</td>
                  <td>{user.username}</td>
                  <td>{roleLabels[user.role]}</td>
                  <td>
                    <input
                      value={resetPassword}
                      onChange={(event) => setResetPassword(event.target.value)}
                      placeholder="New password"
                      type="password"
                    />
                    <button type="button" onClick={() => resetUserPassword(user.id)}>Reset</button>
                  </td>
                  <td>
                    <button type="button" disabled={user.id === currentUserId} onClick={() => deleteUser(user.id)}>
                      Delete
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
    </section>
  );
}
