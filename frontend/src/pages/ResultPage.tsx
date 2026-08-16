import { useState, useEffect, useCallback } from 'react';
import { useLocation, useNavigate, useSearchParams } from 'react-router-dom';
import { useRef } from 'react';
import { Alert, Card, Tabs, Typography, Spin, Tag, Row, Col, Button, Result, Space, Divider, Progress, Collapse, Table, Modal, Input, message } from 'antd';
import { ReloadOutlined, EditOutlined, SaveOutlined } from '@ant-design/icons';
import BudgetPreview from '../components/BudgetPreview';
import ProductCard from '../components/ProductCard';
import CompareTable from '../components/CompareTable';
import Disclaimer from '../components/Disclaimer';
import { fetchRecommend } from '../api/recommend';
import { fetchRecommendationDetail, saveProfile } from '../api/auth';
import type { UserProfile, RecommendationResult, ProductItem } from '../types';

const { Title, Text, Paragraph } = Typography;

export default function ResultPage() {
  const location = useLocation();
  const navigate = useNavigate();
  const [searchParams] = useSearchParams();
  const recordId = searchParams.get('recordId');
  const stateProfile = location.state?.profile as UserProfile | undefined;
  const [profile, setProfile] = useState<UserProfile | null>(stateProfile ?? null);
  const [result, setResult] = useState<RecommendationResult | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [saveModalOpen, setSaveModalOpen] = useState(false);
  const [saveName, setSaveName] = useState('');
  const [saving, setSaving] = useState(false);
  const historyRequestRef = useRef<{ recordId: string; requestVersion: number } | null>(null);

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

  useEffect(() => {
    if (stateProfile) {
      void doRecommend();
    }
  }, [stateProfile, doRecommend]);

  useEffect(() => {
    if (stateProfile) {
      historyRequestRef.current = null;
      return;
    }
    if (!recordId) {
      historyRequestRef.current = null;
      setLoading(false);
      return;
    }

    // The history fetch updates `profile`, which changes `doRecommend`. Keep
    // this effect independent from that callback and guard the route key so
    // React StrictMode's development remount cannot issue a duplicate GET.
    if (historyRequestRef.current?.recordId === recordId) return;
    const requestVersion = (historyRequestRef.current?.requestVersion ?? 0) + 1;
    historyRequestRef.current = { recordId, requestVersion };
    setLoading(true);
    setResult(null);
    setError(null);
    setProfile(null);
    (async () => {
      try {
        const record = await fetchRecommendationDetail(Number(recordId));
        if (historyRequestRef.current?.requestVersion !== requestVersion) return;
        setProfile(record.profile as unknown as UserProfile);
        setResult(record.result);
      } catch (err: unknown) {
        if (historyRequestRef.current?.requestVersion !== requestVersion) return;
        const status = (err as { response?: { status?: number } }).response?.status;
        if (status === 404) {
          setError('该推荐记录不存在或已被删除');
        } else if (status === 403) {
          setError('您无权查看该推荐记录');
        } else if (status === 401) {
          setError('请先登录后再查看推荐记录');
        } else {
          setError('推荐记录加载失败，请稍后重试');
        }
      } finally {
        if (historyRequestRef.current?.requestVersion === requestVersion) setLoading(false);
      }
    })();
  }, [recordId, stateProfile]);

  const handleSaveProfile = async () => {
    if (!profile) return;
    setSaving(true);
    try {
      await saveProfile(saveName.trim() || '未命名画像', profile as unknown as Record<string, unknown>);
      setSaveModalOpen(false);
      setSaveName('');
      message.success('画像已保存，可在“我的账户”中管理');
    } catch {
      message.error('画像保存失败，请稍后重试');
    } finally {
      setSaving(false);
    }
  };

  if (loading) {
    return <div style={{ padding: 40, textAlign: 'center' }}><Spin size="large" tip="正在加载..." /></div>;
  }
  if (error) {
    return (
      <div style={{ maxWidth: 520, margin: '80px auto' }}>
        <Result
          status="error"
          title="加载失败"
          subTitle={error}
          extra={[
            <Button key="back" type="primary" onClick={() => navigate('/')}>返回首页</Button>,
            <Button key="retry" onClick={() => { if (profile) { doRecommend(); } else { window.location.reload(); } }}>重新尝试</Button>,
          ]}
        />
      </div>
    );
  }
  if (!profile) return <div style={{ padding: 40, textAlign: 'center' }}>请先填写问卷信息</div>;
  if (!result) return null;

  const allProducts: ProductItem[] = [...new Map(
    result.packages.flatMap((p) => p.products).map((p) => [p.id, p])
  ).values()];

  const packageTotals = result.packages.map((p) => p.total_premium);
  const packageMaxes = result.packages.map((p) => p.total_premium_max ?? p.total_premium);
  const quoteMin = packageTotals.length ? Math.min(...packageTotals) : null;
  const quoteMax = packageMaxes.length ? Math.max(...packageMaxes) : null;
  const quoteUnknownMax = result.packages.some((p) => p.products.some((pp) => pp.premium_max == null));

  // 画像评估（TASK-029）：历史记录可能缺该字段，全部走可选链容忍
  const assessment = result.profile_assessment;
  const unknownConditions = assessment?.health?.unknown_conditions ?? [];
  const markedTypes = assessment?.coverage?.marked_types ?? [];
  const coverageLabelText = Object.values(assessment?.coverage?.labels ?? {}).join('、');

  const formatPkgTotal = (pkg: { total_premium: number; total_premium_max: number | null }) => {
    if (pkg.total_premium_max != null && pkg.total_premium_max > pkg.total_premium) {
      return `¥${pkg.total_premium.toLocaleString()}~¥${pkg.total_premium_max.toLocaleString()}`;
    }
    return `¥${pkg.total_premium.toLocaleString()}起`;
  };

  const engineModeLabel = result.engine_mode === 'ai' ? 'AI 解释模式' : result.engine_mode === 'degraded' ? '降级模式（AI 繁忙，已自动切换）' : '极速规则模式';
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
      <div className="result-header" style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 16 }}>
        <div>
          <Title level={3} style={{ margin: 0 }}>推荐方案</Title>
          <Tag color={result.engine_mode === 'ai' ? 'blue' : result.engine_mode === 'degraded' ? 'orange' : 'green'} style={{ marginTop: 4 }}>
            {engineModeLabel}
          </Tag>
        </div>
        <Space>
          <Button icon={<SaveOutlined />} onClick={() => setSaveModalOpen(true)}>保存画像</Button>
          <Button icon={<ReloadOutlined />} onClick={doRecommend}>重新推荐</Button>
          <Button icon={<EditOutlined />} onClick={() => navigate('/', { state: { profile } })}>修改信息</Button>
        </Space>
      </div>
      <Divider style={{ margin: '0 0 16px' }} />
      <Text type="secondary" style={{ fontSize: 12, display: 'block', marginBottom: 8 }}>
        保费为产品报价区间（区间下限~上限）；预算建议为估算值。标注「起」表示该产品未披露保费上限，最终价格以核保结论与官方条款为准。
      </Text>

      <Row gutter={16} style={{ marginTop: 16 }}>
        <Col xs={24} sm={12}>
          <BudgetPreview
            annualIncome={result.budget_analysis.annual_income}
            totalBudget={result.budget_analysis.total_budget}
            allocation={result.budget_analysis.allocation}
            quoteMin={quoteMin}
            quoteMax={quoteMax}
            quoteUnknownMax={quoteUnknownMax}
          />
        </Col>
        <Col xs={24} sm={12}>
          <Card title="建议保额" size="small">
            <Row gutter={[8, 8]}>
              {[
                { label: '医疗险', value: result.sum_insured_advice.medical, note: '报销型·百万医疗标配' },
                { label: '意外险', value: result.sum_insured_advice.accident, note: '年收入×8~10倍' },
                { label: '重疾险', value: result.sum_insured_advice.critical_illness, note: '年收入×3+30万基准' },
                { label: '定期寿险', value: result.sum_insured_advice.life, note: '年收入×5+负债估算' },
                { label: '防癌险', value: result.sum_insured_advice.cancer, note: '高龄/健康异常替代保障' },
              ].map((item) => (
                <Col xs={12} sm={8} key={item.label}>
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

      {(unknownConditions.length > 0 || markedTypes.length > 0) && (
        <Card title="画像评估提示" size="small" style={{ marginTop: 16 }}>
          {unknownConditions.length > 0 && (
            <Alert
              type="warning"
              showIcon
              message="未识别健康项"
              description={`${unknownConditions.join('、')}：该健康项本次仅作记录展示，不参与规则筛选，也不构成承保判断；如需核保结论，请以产品健康告知和保险公司核保为准。`}
              style={{ marginBottom: markedTypes.length > 0 ? 12 : 0 }}
            />
          )}
          {markedTypes.length > 0 && (
            <Alert
              type="info"
              showIcon
              message="重复保障提示"
              description={`检测到已有保障（${coverageLabelText || markedTypes.join('、')}），以下险种可能与既有保单责任重叠：${markedTypes.join('、')}。建议加保前先核对既有保单条款，本提示不构成承保判断。`}
            />
          )}
        </Card>
      )}

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
          label: `${pkg.tag_label} (${formatPkgTotal(pkg)}/年)`,
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

      <Modal
        title="保存健康画像"
        open={saveModalOpen}
        onOk={handleSaveProfile}
        onCancel={() => { setSaveModalOpen(false); setSaveName(''); }}
        okText="保存"
        confirmLoading={saving}
      >
        <Space direction="vertical" style={{ width: '100%' }}>
          <Alert
            type="info"
            showIcon
            message="隐私提示"
            description="画像仅保存在您的账户中，仅您本人可见，不会被公开或用于其他用途；可随时在“我的账户”中编辑或删除。"
          />
          <div>
            <Text strong>画像名称</Text>
            <Input
              placeholder="如：2026年家庭保障方案"
              value={saveName}
              onChange={(e) => setSaveName(e.target.value)}
              maxLength={120}
            />
          </div>
        </Space>
      </Modal>
    </div>
  );
}
