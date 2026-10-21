import { Alert } from 'antd';
import { useI18n } from '../i18n';

export default function Disclaimer() {
  const { t } = useI18n();
  return (
    <Alert
      type="info"
      showIcon
      message={t('disclaimer.title')}
      description={t('disclaimer.body')}
      style={{ marginTop: 24 }}
    />
  );
}
