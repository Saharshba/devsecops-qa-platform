import { NavLink, Navigate, Route, Routes, useLocation } from 'react-router-dom';
import { AuthProvider, useAuth } from './auth';
import Dashboard from './pages/Dashboard';
import IssueDetail from './pages/IssueDetail';
import Login from './pages/Login';
import Notifications from './pages/Notifications';
import ProjectBoard from './pages/ProjectBoard';
import Projects from './pages/Projects';

const NAV = [
  { to: '/', label: 'Dashboard', end: true },
  { to: '/projects', label: 'Projects' },
  { to: '/notifications', label: 'Notifications' },
];

function RequireAuth({ children }) {
  const { user } = useAuth();
  const location = useLocation();
  if (!user) return <Navigate to="/login" state={{ from: location }} replace />;
  return children;
}

function Shell({ children }) {
  const { user, logout } = useAuth();
  return (
    <div className="shell">
      <nav className="sidebar">
        <div className="brand">
          Issue Tracker
          <span>Secure delivery</span>
        </div>
        {NAV.map((item) => (
          <NavLink key={item.to} to={item.to} end={item.end}
                   className={({ isActive }) => `nav-link${isActive ? ' active' : ''}`}>
            {item.label}
          </NavLink>
        ))}
        <div className="sidebar-footer">
          <div data-testid="current-user">{user.username} · {user.role}</div>
          <button style={{ marginTop: 8 }} onClick={logout} data-testid="sign-out">Sign out</button>
        </div>
      </nav>
      <main className="main">{children}</main>
    </div>
  );
}

export default function App() {
  return (
    <AuthProvider>
      <Routes>
        <Route path="/login" element={<Login />} />
        <Route
          path="/*"
          element={
            <RequireAuth>
              <Shell>
                <Routes>
                  <Route index element={<Dashboard />} />
                  <Route path="projects" element={<Projects />} />
                  <Route path="projects/:projectKey" element={<ProjectBoard />} />
                  <Route path="issues/:issueKey" element={<IssueDetail />} />
                  <Route path="notifications" element={<Notifications />} />
                  <Route path="*" element={<Navigate to="/" replace />} />
                </Routes>
              </Shell>
            </RequireAuth>
          }
        />
      </Routes>
    </AuthProvider>
  );
}
