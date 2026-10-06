import { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { useAuth } from '../auth';
import { Card, ErrorBanner } from '../components/common';

export default function Login() {
  const { login } = useAuth();
  const navigate = useNavigate();
  const [username, setUsername] = useState('');
  const [password, setPassword] = useState('');
  const [error, setError] = useState(null);
  const [busy, setBusy] = useState(false);

  async function submit(event) {
    event.preventDefault();
    setBusy(true);
    setError(null);
    try {
      await login(username, password);
      navigate('/', { replace: true });
    } catch (err) {
      setError(err);
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="login-page">
      <div className="login-card">
        <Card title="Issue Tracker" note="Sign in to continue.">
          <form onSubmit={submit}>
            <ErrorBanner error={error} />
            <label htmlFor="username">Username</label>
            <input id="username" name="username" autoComplete="username" value={username}
                   onChange={(e) => setUsername(e.target.value)} required />
            <label htmlFor="password">Password</label>
            <input id="password" name="password" type="password" autoComplete="current-password"
                   value={password} onChange={(e) => setPassword(e.target.value)} required />
            <button className="primary" type="submit" disabled={busy} data-testid="sign-in">
              {busy ? 'Signing in…' : 'Sign in'}
            </button>
          </form>
        </Card>
      </div>
    </div>
  );
}
