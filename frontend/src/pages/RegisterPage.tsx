import { useState } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import { Button, Card, Form, Input, Typography, message } from 'antd';
import { register } from '../api/auth';

const { Text, Title } = Typography;

export default function RegisterPage() {
  const [loading, setLoading] = useState(false);
  const navigate = useNavigate();

  return (
    <Card style={{ maxWidth: 420, margin: '48px auto', padding: '0 16px' }}>
      <Title level={3}>注册账号</Title>
      <Text type="secondary">首个注册用户会自动成为管理员；后续用户默认为普通用户。</Text>
      <Form layout="vertical" style={{ marginTop: 24 }} onFinish={async (values) => {
        setLoading(true);
        try {
          await register(values.email, values.password, values.full_name);
          message.success('注册成功');
          navigate('/account', { replace: true });
        } catch {
          message.error('注册失败，邮箱可能已被使用');
        } finally {
          setLoading(false);
        }
      }}>
        <Form.Item name="full_name" label="姓名">
          <Input autoComplete="name" />
        </Form.Item>
        <Form.Item name="email" label="邮箱" rules={[{ required: true }, { type: 'email' }]}>
          <Input autoComplete="email" />
        </Form.Item>
        <Form.Item name="password" label="密码" rules={[{ required: true, min: 8 }]}>
          <Input.Password autoComplete="new-password" />
        </Form.Item>
        <Button type="primary" htmlType="submit" loading={loading} block>注册</Button>
      </Form>
      <Text type="secondary" style={{ display: 'block', marginTop: 16 }}>
        已有账号？<Link to="/login">登录</Link>
      </Text>
    </Card>
  );
}
