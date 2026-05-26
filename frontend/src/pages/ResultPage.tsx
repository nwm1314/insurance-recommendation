import { useState, useEffect, useCallback } from 'react';
import { useLocation, useNavigate } from 'react-router-dom';
import { Card, Tabs, Typography, Spin, Tag, Row, Col, Button, Result, Space, Divider } from 'antd';
import { ReloadOutlined, EditOutlined } from '@ant-design/icons';
import BudgetPreview from '../components/BudgetPreview';
import ProductCard from '../components/ProductCard';
import CompareTable from '../components/CompareTable';
import Disclaimer from '../components/Disclaimer';
import { fetchRecommend } from '../api/recommend';
import type { UserProfile, RecommendationResult, ProductItem } from '../types';

const { Title, Text, Paragraph } = Typography;

export default function ResultPage() {
  const location = useLocation();
  const navigate = useNavigate();
  const profile = location.state?.profile as UserProfile;
  const [result, setResult] = useState<RecommendationResult | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const doRecommend = useCallback(async () => {
    if (!profile) return;
    setLoading(true);
    setResult(null);
    setError(null);
    try {
      const data = await fetchRecommend(profile);
      setResult(data);
    } catch (err: unknown) {
      const axiosErr = err as { response?: { data?: { detail?: unknown } }; message?: string };
      const detail = axiosErr.response?.data?.detail;
      const msg = Array.isArray(detail)
        ? `请返回上页完善信息：${detail.map((d: { loc: string[]; msg: string }) => d.msg).join('；')}`
        : typeof detail === 'string'
          ? detail
          : (axiosErr.message || '推荐服务异常，请稍后重试');
      setError(msg);
    } finally {
      setLoading(false);
    }
  }, [profile]);

  useEffect(() => { doRecommend(); }, []);

  if (!profile) return <div style={{ padding: 40, textAlign: 'center' }}>请先填写问卷信息</div>;
  if (loading) {
    return <div style={{ padding: 40, textAlign: 'center' }}><Spin size="large" tip="正在分析推荐..." /></div>;
  }
  if (error) {
    return (
      <div style={{ maxWidth: 520, margin: '80px auto' }}>
        <Result
          status="error"
          title="推荐失败"
          subTitle={error}
          extra={[
            <Button key="back" type="primary" onClick={() => navigate('/')}>返回修改信息</Button>,
            <Button key="retry" onClick={doRecommend}>重新尝试</Button>,
          ]}
        />
      </div>
    );
  }
  if (!result) return null;

  const allProducts: ProductItem[] = [...new Map(
    result.packages.flatMap((p) => p.products).map((p) => [p.id, p])
  ).values()];

  const engineModeLabel = result.engine_mode === 'ai' ? 'AI 专家模式' : result.engine_mode === 'degraded' ? '降级模式（AI 繁忙，已自动切换）' : '极速规则模式';

  return (
    <div style={{ maxWidth: 960, margin: '24px auto', padding: '0 16px' }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 16 }}>
        <div>
          <Title level={3} style={{ margin: 0 }}>推荐方案</Title>
          <Tag color={result.engine_mode === 'ai' ? 'blue' : result.engine_mode === 'degraded' ? 'orange' : 'green'} style={{ marginTop: 4 }}>
            {engineModeLabel}
          </Tag>
        </div>
        <Space>
          <Button icon={<ReloadOutlined />} onClick={doRecommend}>重新推荐</Button>
          <Button icon={<EditOutlined />} onClick={() => navigate('/')}>修改信息</Button>
        </Space>
      </div>
      <Divider style={{ margin: '0 0 16px' }} />

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
            <Row gutter={[8, 8]}>
              {[
                { label: '医疗险', value: result.sum_insured_advice.medical, note: '报销型·百万医疗标配' },
                { label: '意外险', value: result.sum_insured_advice.accident, note: '年收入×8~10倍' },
                { label: '重疾险', value: result.sum_insured_advice.critical_illness, note: '年收入×3+30万基准' },
                { label: '定期寿险', value: result.sum_insured_advice.life, note: '年收入×5+负债估算' },
              ].map((item) => (
                <Col span={12} key={item.label}>
                  <div style={{ marginBottom: 8 }}>
                    <Text type="secondary" style={{ fontSize: 11 }}>{item.label}</Text>
                    <div style={{ fontWeight: 700, fontSize: 17, color: '#1677ff' }}>
                      {(item.value / 10000).toFixed(0)}<span style={{ fontSize: 12, fontWeight: 400 }}>万</span>
                    </div>
                    <Text type="secondary" style={{ fontSize: 10 }}>{item.note}</Text>
                  </div>
                </Col>
              ))}
            </Row>
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
