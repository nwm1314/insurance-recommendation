import { useState, useEffect, useCallback } from 'react';
import { useLocation, useNavigate } from 'react-router-dom';
import { Alert, Card, Tabs, Typography, Spin, Tag, Row, Col, Button, Result, Space, Divider, Progress, Collapse, Table } from 'antd';
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
  const reasonCodeLabel = (code: string) => ({
    inactive: '停售',
    type_forbidden: '硬规则禁推',
    type_not_in_plan: '不在方案层级',
    age_not_allowed: '年龄不符',
    job_class_not_allowed: '职业不符',
    over_budget: '预算不足',
    unknown: '其他',
  }[code] || code);

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
                { label: '防癌险', value: result.sum_insured_advice.cancer, note: '高龄/健康异常替代保障' },
              ].map((item) => (
                <Col span={8} key={item.label}>
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

      {result.ai_explanation && (
        <Card title="AI 结构化解释" size="small" style={{ marginTop: 16 }}>
          {result.ai_explanation.summary && <Paragraph>{result.ai_explanation.summary}</Paragraph>}
          <Row gutter={12}>
            {result.ai_explanation.reasoning.length > 0 && (
              <Col xs={24} md={8}>
                <Text strong>推荐理由</Text>
                <ul style={{ paddingLeft: 18, marginBottom: 0 }}>
                  {result.ai_explanation.reasoning.map((item) => <li key={item}>{item}</li>)}
                </ul>
              </Col>
            )}
            {result.ai_explanation.comparison_notes.length > 0 && (
              <Col xs={24} md={8}>
                <Text strong>对比说明</Text>
                <ul style={{ paddingLeft: 18, marginBottom: 0 }}>
                  {result.ai_explanation.comparison_notes.map((item) => <li key={item}>{item}</li>)}
                </ul>
              </Col>
            )}
            {result.ai_explanation.risk_notes.length > 0 && (
              <Col xs={24} md={8}>
                <Text strong>注意事项</Text>
                <ul style={{ paddingLeft: 18, marginBottom: 0 }}>
                  {result.ai_explanation.risk_notes.map((item) => <li key={item}>{item}</li>)}
                </ul>
              </Col>
            )}
          </Row>
        </Card>
      )}

      {(result.hard_rule_summary.length > 0 || result.coverage_gap_summary.length > 0 || result.not_recommended_summary.length > 0) && (
        <Card title="推荐解释" size="small" style={{ marginTop: 16 }}>
          {result.hard_rule_summary.length > 0 && (
            <Alert
              type="success"
              showIcon
              message="硬性规则已先执行"
              description={result.hard_rule_summary.join('；')}
              style={{ marginBottom: 12 }}
            />
          )}
          {result.coverage_gap_summary.length > 0 && (
            <Alert
              type="warning"
              showIcon
              message="保障缺口提示"
              description={result.coverage_gap_summary.join('；')}
              style={{ marginBottom: result.not_recommended_summary.length > 0 ? 12 : 0 }}
            />
          )}
          {result.not_recommended_summary.length > 0 && (
            <>
              <Alert
                type="info"
                showIcon
                message="未推荐原因"
                description={result.not_recommended_summary.map((item) => `${reasonCodeLabel(item.reason_code)}：${item.count}款`).join('；')}
                style={{ marginBottom: result.not_recommended_details.length > 0 ? 12 : 0 }}
              />
              {result.not_recommended_details.length > 0 && (
                <Collapse
                  size="small"
                  items={[
                    {
                      key: 'not-recommended-details',
                      label: `查看未推荐产品明细（最多展示 ${result.not_recommended_details.length} 款）`,
                      children: (
                        <Table
                          size="small"
                          rowKey={(row) => `${row.product_id}-${row.name}`}
                          pagination={false}
                          dataSource={result.not_recommended_details}
                          columns={[
                            { title: '产品', dataIndex: 'name', key: 'name' },
                            { title: '险种', dataIndex: 'type', key: 'type', width: 100 },
                            { title: '原因类型', dataIndex: 'reason_code', key: 'reason_code', width: 120, render: (code: string) => reasonCodeLabel(code) },
                            { title: '未推荐原因', dataIndex: 'reason', key: 'reason' },
                          ]}
                        />
                      ),
                    },
                  ]}
                />
              )}
            </>
          )}
        </Card>
      )}

      <Tabs
        style={{ marginTop: 16 }}
        items={result.packages.map((pkg) => ({
          key: pkg.tag,
          label: `${pkg.tag_label} (¥${pkg.total_premium.toLocaleString()}/年)`,
          children: (
            <div>
              <Card size="small" style={{ marginBottom: 12 }}>
                <Row gutter={16} align="middle">
                  <Col xs={24} sm={8}>
                    <Text type="secondary">预算利用率</Text>
                    <Progress percent={Math.round(pkg.budget_utilization * 100)} size="small" />
                  </Col>
                  <Col xs={24} sm={8}>
                    <Text type="secondary">方案完整度</Text>
                    <Progress percent={Math.round(pkg.completeness_score * 100)} size="small" status={pkg.completeness_score >= 0.8 ? 'success' : 'active'} />
                  </Col>
                  <Col xs={24} sm={8}>
                    {pkg.coverage_gap_notes.length > 0 ? (
                      <Text type="warning">{pkg.coverage_gap_notes.join('；')}</Text>
                    ) : (
                      <Text type="success">当前方案主要保障层配置完整</Text>
                    )}
                  </Col>
                </Row>
              </Card>
              {pkg.products.map((p) => (
                <div key={p.id}>
                  <ProductCard product={p} />
                  {p.recommendation_reasons.length > 0 && (
                    <Card size="small" style={{ margin: '-8px 0 12px' }}>
                      <Text type="secondary">推荐理由：</Text>
                      <Space wrap style={{ marginLeft: 8 }}>
                        {p.recommendation_reasons.map((reason) => <Tag key={reason} color="blue">{reason}</Tag>)}
                      </Space>
                    </Card>
                  )}
                </div>
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
