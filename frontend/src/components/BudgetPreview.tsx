import { Card, Row, Col, Typography } from 'antd';
import { useI18n } from '../i18n';
import type { MessageKey } from '../i18n/messages';

const { Text } = Typography;

interface Props {
  annualIncome: number;
  totalBudget: number;
  allocation: { medical: number; accident: number; critical_illness: number; life: number; cancer: number };
  quoteMin?: number | null;
  quoteMax?: number | null;
  quoteUnknownMax?: boolean;
}

const ALLOCATION_ITEMS: { key: 'medical' | 'accident' | 'critical_illness' | 'life' | 'cancer'; label: MessageKey; note: MessageKey; color: string }[] = [
  { key: 'medical', label: 'budget.allocMedical', note: 'budget.allocMedicalNote', color: '#1677ff' },
  { key: 'accident', label: 'budget.allocAccident', note: 'budget.allocAccidentNote', color: '#52c41a' },
  { key: 'critical_illness', label: 'budget.allocCritical', note: 'budget.allocCriticalNote', color: '#faad14' },
  { key: 'life', label: 'budget.allocLife', note: 'budget.allocLifeNote', color: '#722ed1' },
  { key: 'cancer', label: 'budget.allocCancer', note: 'budget.allocCancerNote', color: '#eb2f96' },
];

export default function BudgetPreview({ annualIncome, totalBudget, allocation, quoteMin, quoteMax, quoteUnknownMax }: Props) {
  const { t } = useI18n();
  const ratioPct = ((totalBudget / annualIncome) * 100).toFixed(1);
  const pct = (v: number) => Math.round(v * 100);
  const budgetMin = Math.round(totalBudget * 0.85);
  const budgetMax = Math.round(totalBudget * 1.15);
  const quoteOverBudget = quoteMax != null && quoteMax > totalBudget;

  const formatQuote = (): string => {
    if (quoteMin == null) return t('budget.quoteEmpty');
    if (quoteMax != null && quoteMax > quoteMin) {
      return `¥${quoteMin.toLocaleString()}~¥${quoteMax.toLocaleString()}${t('home.perYearSuffix')}`;
    }
    return `¥${quoteMin.toLocaleString()}${t('common.fromSuffix')}${t('home.perYearSuffix')}`;
  };

  return (
    <Card title={t('budget.title')} size="small">
      <Row gutter={8} style={{ marginBottom: 12 }}>
        <Col xs={24} sm={8}>
          <Text type="secondary" style={{ fontSize: 11 }}>{t('budget.annualIncome')}</Text>
          <div style={{ fontWeight: 700, fontSize: 16 }}>
            ¥{(annualIncome / 10000).toFixed(0)}<span style={{ fontSize: 12, fontWeight: 400 }}>{t('common.unitWan')}</span>
          </div>
        </Col>
        <Col xs={24} sm={8}>
          <Text type="secondary" style={{ fontSize: 11 }}>{t('budget.suggestion')}</Text>
          <div style={{ fontWeight: 700, fontSize: 16, color: '#1677ff' }}>
            {t('budget.about', { amount: totalBudget.toLocaleString() })}
          </div>
          <Text type="secondary" style={{ fontSize: 10 }}>
            {t('budget.range', { min: budgetMin.toLocaleString(), max: budgetMax.toLocaleString() })}
          </Text>
        </Col>
        <Col xs={24} sm={8}>
          <Text type="secondary" style={{ fontSize: 11 }}>{t('budget.share')}</Text>
          <div style={{ fontWeight: 700, fontSize: 16 }}>{ratioPct}<span style={{ fontSize: 12, fontWeight: 400 }}>%</span></div>
        </Col>
      </Row>
      <div style={{ marginBottom: 12, padding: '8px 10px', background: '#f6ffed', border: '1px solid #b7eb8f', borderRadius: 4 }}>
        <Text type="secondary" style={{ fontSize: 11 }}>{t('budget.quoteRange')}</Text>
        <div style={{ fontWeight: 700, fontSize: 16, color: quoteOverBudget ? '#ff4d4f' : '#389e0d' }}>
          {formatQuote()}
        </div>
        <Text type="secondary" style={{ fontSize: 10 }}>
          {quoteOverBudget
            ? t('budget.overBudget')
            : quoteUnknownMax
              ? t('budget.unknownMax')
              : t('budget.finalNote')}
        </Text>
      </div>
      <div>
        {ALLOCATION_ITEMS.map((item) => {
          const v = pct(allocation[item.key]);
          return (
            <div key={item.key} style={{ marginBottom: 6 }}>
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 2 }}>
                <span style={{ fontSize: 12 }}>
                  <span style={{ display: 'inline-block', width: 6, height: 6, borderRadius: '50%', background: item.color, marginRight: 4, verticalAlign: 'middle' }} />
                  {t(item.label)}
                </span>
                <span style={{ fontSize: 12, fontWeight: 500 }}>{v}%</span>
              </div>
              <div style={{ height: 4, borderRadius: 2, background: '#f0f0f0' }}>
                <div style={{ height: 4, borderRadius: 2, background: item.color, width: `${Math.max(v, 2)}%`, transition: 'width 0.3s' }} />
              </div>
              <Text type="secondary" style={{ fontSize: 10 }}>{t(item.note)}</Text>
            </div>
          );
        })}
      </div>
    </Card>
  );
}
