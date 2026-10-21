import { useState } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import { Button, Card, Form, Input, Typography, message } from 'antd';
import { register } from '../api/auth';
import { useI18n } from '../i18n';

const { Text, Title } = Typography;

export default function RegisterPage() {
  const { t } = useI18n();
  const [loading, setLoading] = useState(false);
  const navigate = useNavigate();

  return (
    <Card style={{ maxWidth: 420, margin: '48px auto', padding: '0 16px' }}>
      <Title level={3}>{t('auth.registerTitle')}</Title>
      <Text type="secondary">{t('auth.registerSubtitle')}</Text>
      <Form layout="vertical" style={{ marginTop: 24 }} onFinish={async (values) => {
        setLoading(true);
        try {
          await register(values.email, values.password, values.full_name);
          message.success(t('auth.registerSuccess'));
          navigate('/account', { replace: true });
        } catch {
          message.error(t('auth.registerFailed'));
        } finally {
          setLoading(false);
        }
      }}>
        <Form.Item name="full_name" label={t('auth.fullName')}>
          <Input autoComplete="name" />
        </Form.Item>
        <Form.Item name="email" label={t('auth.email')} rules={[{ required: true }, { type: 'email' }]}>
          <Input autoComplete="email" />
        </Form.Item>
        <Form.Item name="password" label={t('auth.password')} rules={[{ required: true, min: 8 }]}>
          <Input.Password autoComplete="new-password" />
        </Form.Item>
        <Button type="primary" htmlType="submit" loading={loading} block>{t('auth.registerButton')}</Button>
      </Form>
      <Text type="secondary" style={{ display: 'block', marginTop: 16 }}>
        {t('auth.hasAccount')}<Link to="/login">{t('auth.loginLink')}</Link>
      </Text>
    </Card>
  );
}
