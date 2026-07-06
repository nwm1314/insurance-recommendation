import { useState } from 'react';
import { Link, useLocation, useNavigate } from 'react-router-dom';
import { Button, Card, Form, Input, Typography, message } from 'antd';
import { login } from '../api/auth';

const { Text, Title } = Typography;

export default function LoginPage() {
  const [loading, setLoading] = useState(false);
  const navigate = useNavigate();
  const location = useLocation();
  const from = (location.state as { from?: { pathname?: string } } | null)?.from?.pathname || '/account';

  return (
    <Card style={{ maxWidth: 420, margin: '48px auto' }}>
      <Title level={3}>登录账号</Title>
      <Text type="secondary">登录后可保存推荐历史，并按权限访问管理后台。</Text>
      <Form layout="vertical" style={{ marginTop: 24 }} onFinish={async (values) => {
        setLoading(true);
        try {
          await login(values.email, values.password);
          message.success('登录成功');
          navigate(from, { replace: true });
        } catch {
          message.error('邮箱或密码错误');
        } finally {
          setLoading(false);
        }
      }}>
        <Form.Item name="email" label="邮箱" rules={[{ required: true }, { type: 'email' }]}>
          <Input autoComplete="email" />
        </Form.Item>
        <Form.Item name="password" label="密码" rules={[{ required: true }]}>
          <Input.Password autoComplete="current-password" />
        </Form.Item>
        <Button type="primary" htmlType="submit" loading={loading} block>登录</Button>
      </Form>
      <Text type="secondary" style={{ display: 'block', marginTop: 16 }}>
        还没有账号？<Link to="/register">注册</Link>
      </Text>
    </Card>
  );
}
