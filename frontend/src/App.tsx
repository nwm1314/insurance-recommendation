import { Routes, Route, Link } from 'react-router-dom';
import { Layout, Menu } from 'antd';
import { HomeOutlined, SearchOutlined, SettingOutlined } from '@ant-design/icons';
import HomePage from './pages/HomePage';
import ResultPage from './pages/ResultPage';
import AdminPage from './pages/AdminPage';

const { Header, Content } = Layout;

export default function App() {
  return (
    <Layout style={{ minHeight: '100vh' }}>
      <Header>
        <Menu theme="dark" mode="horizontal" defaultSelectedKeys={['home']}
          items={[
            { key: 'home', icon: <HomeOutlined />, label: <Link to="/">首页问卷</Link> },
            { key: 'result', icon: <SearchOutlined />, label: <Link to="/result">推荐结果</Link> },
            { key: 'admin', icon: <SettingOutlined />, label: <Link to="/admin">管理后台</Link> },
          ]}
        />
      </Header>
      <Content>
        <Routes>
          <Route path="/" element={<HomePage />} />
          <Route path="/result" element={<ResultPage />} />
          <Route path="/admin" element={<AdminPage />} />
        </Routes>
      </Content>
    </Layout>
  );
}
