import { Steps } from 'antd';
import { useI18n } from '../i18n';

interface Props {
  current: number;
}

export default function ProgressSteps({ current }: Props) {
  const { t } = useI18n();
  const steps = [
    { title: t('steps.basic') },
    { title: t('steps.career') },
    { title: t('steps.health') },
    { title: t('steps.preferences') },
  ];
  return <Steps current={current} items={steps} style={{ marginBottom: 32 }} />;
}
