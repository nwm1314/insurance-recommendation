import { Routes, Route, Link, useLocation } from 'react-router-dom';
import { Layout, Menu, Typography } from 'antd';
import { HomeOutlined, SearchOutlined, SettingOutlined } from '@ant-design/icons';
import HomePage from './pages/HomePage';
import ResultPage from './pages/ResultPage';
import AdminPage from './pages/AdminPage';

const { Header, Content, Footer } = Layout;

export default function App() {
  const location = useLocation();
  const selectedKey = location.pathname === '/' ? 'home'
    : location.pathname === '/result' ? 'result'
    : location.pathname === '/admin' ? 'admin'
    : 'home';

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
        <Menu theme="dark" mode="horizontal" selectedKeys={[selectedKey]} style={{ flex: 1, minWidth: 0 }}
          items={[
            { key: 'home', icon: <HomeOutlined />, label: <Link to="/">填写问卷</Link> },
            { key: 'result', icon: <SearchOutlined />, label: <Link to="/result">推荐结果</Link> },
            { key: 'admin', icon: <SettingOutlined />, label: <Link to="/admin">管理后台</Link> },
          ]}
        />
      </Header>
      <Content style={{ padding: '24px', maxWidth: 1040, margin: '0 auto', width: '100%' }}>
        <Routes>
          <Route path="/" element={<HomePage />} />
          <Route path="/result" element={<ResultPage />} />
          <Route path="/admin" element={<AdminPage />} />
        </Routes>
      </Content>
      <Footer style={{ textAlign: 'center', color: '#999', fontSize: 12, padding: '12px' }}>
        本工具生成方案仅供参考，最终承保以保险公司官方条款为准。数据来源：慧择网、开心保、中民保险网及各保险公司官网
      </Footer>
    </Layout>
  );
}
