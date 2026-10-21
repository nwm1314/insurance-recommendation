import { useState } from 'react';
import { Link, useLocation, useNavigate } from 'react-router-dom';
import { Button, Card, Form, Input, Typography, message } from 'antd';
import { login } from '../api/auth';
import { useI18n } from '../i18n';

const { Text, Title } = Typography;

export default function LoginPage() {
  const { t } = useI18n();
  const [loading, setLoading] = useState(false);
  const navigate = useNavigate();
  const location = useLocation();
  const from = (location.state as { from?: { pathname?: string } } | null)?.from?.pathname || '/account';

  return (
    <Card style={{ maxWidth: 420, margin: '48px auto', padding: '0 16px' }}>
      <Title level={3}>{t('auth.loginTitle')}</Title>
      <Text type="secondary">{t('auth.loginSubtitle')}</Text>
      <Form layout="vertical" style={{ marginTop: 24 }} onFinish={async (values) => {
        setLoading(true);
        try {
          await login(values.email, values.password);
          message.success(t('auth.loginSuccess'));
          navigate(from, { replace: true });
        } catch {
          message.error(t('auth.loginFailed'));
        } finally {
          setLoading(false);
        }
      }}>
        <Form.Item name="email" label={t('auth.email')} rules={[{ required: true }, { type: 'email' }]}>
          <Input autoComplete="email" />
        </Form.Item>
        <Form.Item name="password" label={t('auth.password')} rules={[{ required: true }]}>
          <Input.Password autoComplete="current-password" />
        </Form.Item>
        <Button type="primary" htmlType="submit" loading={loading} block>{t('auth.loginButton')}</Button>
      </Form>
      <Text type="secondary" style={{ display: 'block', marginTop: 16 }}>
        {t('auth.noAccount')}<Link to="/register">{t('auth.registerLink')}</Link>
      </Text>
    </Card>
  );
}
