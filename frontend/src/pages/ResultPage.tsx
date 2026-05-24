import { useState, useEffect, useCallback } from 'react';
import { useLocation } from 'react-router-dom';
import { Card, Tabs, Typography, Spin, Tag, Row, Col, Statistic } from 'antd';
import BudgetPreview from '../components/BudgetPreview';
import ProductCard from '../components/ProductCard';
import CompareTable from '../components/CompareTable';
import Disclaimer from '../components/Disclaimer';
import { fetchRecommend, fetchRecommendSSE } from '../api/recommend';
import type { UserProfile, RecommendationResult, ProductItem } from '../types';

const { Title, Paragraph } = Typography;

export default function ResultPage() {
  const location = useLocation();
  const profile = location.state?.profile as UserProfile;
  const [result, setResult] = useState<RecommendationResult | null>(null);
  const [loading, setLoading] = useState(true);

  const loadData = useCallback(async () => {
    if (!profile) return;
    setLoading(true);
    if (profile.enable_llm_engine) {
      fetchRecommendSSE(
        profile,
        (data) => setResult(data),
        () => setLoading(false),
        () => { fetchRecommend(profile).then(setResult).finally(() => setLoading(false)); },
      );
    } else {
      const data = await fetchRecommend(profile);
      setResult(data);
      setLoading(false);
    }
  }, [profile]);

  useEffect(() => { loadData(); }, [loadData]);

  if (!profile) return <div style={{ padding: 40, textAlign: 'center' }}>请先填写问卷信息</div>;
  if (loading && !result) {
    return <div style={{ padding: 40, textAlign: 'center' }}><Spin size="large" tip="正在分析推荐..." /></div>;
  }
  if (!result) return null;

  const allProducts: ProductItem[] = result.packages.flatMap((p) => p.products);

  return (
    <div style={{ maxWidth: 960, margin: '24px auto', padding: '0 16px' }}>
      <Title level={3}>推荐方案</Title>
      <Tag color={result.engine_mode === 'ai' ? 'blue' : result.engine_mode === 'degraded' ? 'orange' : 'green'}>
        {result.engine_mode === 'ai' ? 'AI 专家模式' : result.engine_mode === 'degraded' ? '降级模式' : '极速规则模式'}
      </Tag>

      <Row gutter={16} style={{ marginTop: 16 }}>
        <Col span={12}>
          <BudgetPreview
            annualIncome={result.budget_analysis.annual_income}
            totalBudget={result.budget_analysis.total_budget}
            allocation={result.budget_analysis.allocation}
          />
        </Col>
        <Col span={12}>
          <Card title="建议保额" size="small">
            <Statistic title="医疗险" value={result.sum_insured_advice.medical} suffix="元" />
            <Statistic title="意外险" value={result.sum_insured_advice.accident} suffix="元" />
            <Statistic title="重疾险" value={result.sum_insured_advice.critical_illness} suffix="元" />
            <Statistic title="定期寿险" value={result.sum_insured_advice.life} suffix="元" />
          </Card>
        </Col>
      </Row>

      {result.llm_narrative && (
        <Card style={{ marginTop: 16, background: '#e6f7ff' }}>
          <Paragraph>{result.llm_narrative}</Paragraph>
        </Card>
      )}

      <Tabs
        style={{ marginTop: 16 }}
        items={result.packages.map((pkg) => ({
          key: pkg.tag,
          label: `${pkg.tag_label} (¥${pkg.total_premium.toLocaleString()}/年)`,
          children: (
            <div>
              {pkg.products.map((p) => (
                <ProductCard key={p.id} product={p} />
              ))}
            </div>
          ),
        }))}
      />

      <Card title="横向对比" style={{ marginTop: 16 }}>
        <CompareTable products={allProducts} />
      </Card>

      <Disclaimer />
    </div>
  );
}
