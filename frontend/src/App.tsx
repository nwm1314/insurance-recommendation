import { Component, lazy, Suspense, useEffect, useState, type ReactNode } from 'react';
import { Routes, Route, Link, useLocation } from 'react-router-dom';
import { Button, Drawer, Layout, Menu, Result, Spin, Typography } from 'antd';
import { HomeOutlined, LoginOutlined, MenuOutlined, SearchOutlined, SettingOutlined, UserOutlined } from '@ant-design/icons';
import ProtectedRoute from './components/ProtectedRoute';
import { getStoredUser } from './api/auth';
import './mobile-responsive.css';

const { Header, Content, Footer } = Layout;

// 懒加载 chunk 偶发网络失败时自动重试（最多 2 次，间隔 500ms），
// 仍失败则抛给 RouteErrorBoundary 显示可操作的错误回退。
function retryable<T>(fn: () => Promise<T>, retriesLeft = 2): Promise<T> {
  return fn().catch((err) => {
    if (retriesLeft <= 0) throw err;
    return new Promise((resolve) => setTimeout(resolve, 500)).then(() => retryable(fn, retriesLeft - 1));
  });
}

const HomePage = lazy(() => retryable(() => import('./pages/HomePage')));
const ResultPage = lazy(() => retryable(() => import('./pages/ResultPage')));
const AdminPage = lazy(() => retryable(() => import('./pages/AdminPage')));
const LoginPage = lazy(() => retryable(() => import('./pages/LoginPage')));
const RegisterPage = lazy(() => retryable(() => import('./pages/RegisterPage')));
const AccountPage = lazy(() => retryable(() => import('./pages/AccountPage')));

function RouteFallback() {
  return (
    <div role="status" aria-label="页面加载中" style={{ display: 'flex', justifyContent: 'center', padding: '64px 0' }}>
      <Spin size="large" />
    </div>
  );
}

// 懒加载 chunk 加载失败时兜底：提示 + 重新加载（重试由 retryable 与整页刷新共同覆盖）。
class RouteErrorBoundary extends Component<{ children: ReactNode }, { failed: boolean }> {
  state = { failed: false };

  static getDerivedStateFromError() {
    return { failed: true };
  }

  render() {
    if (this.state.failed) {
      return (
        <Result
          status="warning"
          title="页面加载失败"
          subTitle="网络异常或页面资源加载失败，请重试。"
          extra={<Button type="primary" onClick={() => window.location.reload()}>重新加载</Button>}
        />
      );
    }
    return this.props.children;
  }
}

export default function App() {
  const location = useLocation();
  const [user, setUser] = useState(() => getStoredUser());
  const [drawerOpen, setDrawerOpen] = useState(false);
  const canUseAdmin = Boolean(user?.permissions.includes('crawl:read'));

  useEffect(() => {
    const syncUser = () => setUser(getStoredUser());
    window.addEventListener('auth-changed', syncUser);
    window.addEventListener('storage', syncUser);
    return () => {
      window.removeEventListener('auth-changed', syncUser);
      window.removeEventListener('storage', syncUser);
    };
  }, []);

  const selectedKey = location.pathname === '/' ? 'home'
    : location.pathname === '/result' ? 'result'
    : location.pathname === '/admin' ? 'admin'
    : location.pathname === '/account' ? 'account'
    : location.pathname === '/login' || location.pathname === '/register' ? 'login'
    : 'home';

  const navItems = [
    { key: 'home', icon: <HomeOutlined />, label: <Link to="/" onClick={() => setDrawerOpen(false)}>填写问卷</Link> },
    { key: 'result', icon: <SearchOutlined />, label: <Link to="/result" onClick={() => setDrawerOpen(false)}>推荐结果</Link> },
    user ? { key: 'account', icon: <UserOutlined />, label: <Link to="/account" onClick={() => setDrawerOpen(false)}>我的账号</Link> } : null,
    canUseAdmin ? { key: 'admin', icon: <SettingOutlined />, label: <Link to="/admin" onClick={() => setDrawerOpen(false)}>管理后台</Link> } : null,
    user ? null : { key: 'login', icon: <LoginOutlined />, label: <Link to="/login" onClick={() => setDrawerOpen(false)}>登录/注册</Link> },
  ].filter(Boolean);

  return (
    <Layout style={{ minHeight: '100vh', background: '#f5f5f5' }}>
      <Header style={{ display: 'flex', alignItems: 'center', padding: '0 24px', background: '#001529' }}>
        <Link to="/" style={{ display: 'flex', alignItems: 'center', gap: 8, marginRight: 32, textDecoration: 'none' }}>
          <div style={{
            width: 32, height: 32, borderRadius: 8,
            background: 'linear-gradient(135deg, #1677ff, #69b1ff)',
            display: 'flex', alignItems: 'center', justifyContent: 'center',
            color: '#fff', fontWeight: 700, fontSize: 16,
          }}>保</div>
          <Typography.Text style={{ color: '#fff', fontWeight: 600, fontSize: 16, whiteSpace: 'nowrap' }}>
            智能保险推荐
          </Typography.Text>
        </Link>
        <Menu className="desktop-menu" theme="dark" mode="horizontal" selectedKeys={[selectedKey]} style={{ flex: 1, minWidth: 0 }}
          items={navItems}
        />
        <Button className="mobile-menu-button" type="text" icon={<MenuOutlined />} onClick={() => setDrawerOpen(true)} />
      </Header>
      <Drawer
        className="mobile-drawer"
        title="菜单"
        placement="right"
        onClose={() => setDrawerOpen(false)}
        open={drawerOpen}
      >
        <Menu mode="inline" selectedKeys={[selectedKey]} items={navItems} />
      </Drawer>
      <Content style={{ padding: '24px', maxWidth: 1040, margin: '0 auto', width: '100%' }}>
        <RouteErrorBoundary>
          <Suspense fallback={<RouteFallback />}>
            <Routes>
              <Route path="/" element={<HomePage />} />
              <Route path="/result" element={<ResultPage />} />
              <Route path="/login" element={<LoginPage />} />
              <Route path="/register" element={<RegisterPage />} />
              <Route path="/account" element={<ProtectedRoute><AccountPage /></ProtectedRoute>} />
              <Route path="/admin" element={<ProtectedRoute permission="crawl:read"><AdminPage /></ProtectedRoute>} />
            </Routes>
          </Suspense>
        </RouteErrorBoundary>
      </Content>
      <Footer style={{ textAlign: 'center', color: '#999', fontSize: 12, padding: '12px' }}>
        本工具生成方案仅供参考，最终承保以保险公司官方条款为准。数据来源：慧择网、开心保、中民保险网及各保险公司官网
      </Footer>
    </Layout>
  );
}
