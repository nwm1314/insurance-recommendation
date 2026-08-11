import { useState, useEffect } from 'react';
import { Alert, Button, Card, Col, Divider, Drawer, Form, Input, InputNumber, Popconfirm, Row, Select, Space, Statistic, Switch, Table, Tabs, Typography, message } from 'antd';
import apiClient from '../api/client';
import { fetchProducts, createProduct, updateProduct, deleteProduct, fetchProductDetail } from '../api/products';
import { createManualExtraction, createPlatform, updatePlatform, deletePlatform } from '../api/ingestion';
import {
  approveReviewTask,
  createCrawlJob,
  createSourcePage,
  fetchCrawlJobs,
  fetchCrawlRuns,
  fetchIngestionStatus,
  fetchReviewTaskDetail,
  fetchReviewTasks,
  fetchSourcePages,
  fetchSourcePlatforms,
  rejectReviewTask,
  runCrawlJob,
} from '../api/ingestion';
import type { CrawlJob, CrawlRun, IngestionStatus, ReviewTask, ReviewTaskDetail, SourcePage, SourcePlatform } from '../api/ingestion';
import type { ProductInfo } from '../types';
import type { ColumnsType } from 'antd/es/table';

const { Title } = Typography;

export default function AdminPage() {
  const [products, setProducts] = useState<ProductInfo[]>([]);
  const [productTotal, setProductTotal] = useState(0);
  const [productPage, setProductPage] = useState(1);
  const [productPageSize, setProductPageSize] = useState(20);
  const [status, setStatus] = useState<IngestionStatus | null>(null);
  const [platforms, setPlatforms] = useState<SourcePlatform[]>([]);
  const [sourcePages, setSourcePages] = useState<SourcePage[]>([]);
  const [jobs, setJobs] = useState<CrawlJob[]>([]);
  const [runs, setRuns] = useState<CrawlRun[]>([]);
  const [reviewTasks, setReviewTasks] = useState<ReviewTask[]>([]);
  const [reviewDetail, setReviewDetail] = useState<ReviewTaskDetail | null>(null);
  const [loading, setLoading] = useState(false);
  const [runningJobId, setRunningJobId] = useState<number | null>(null);
  const [sourcePageForm] = Form.useForm();
  const [jobForm] = Form.useForm();
  const [productForm] = Form.useForm();
  const [productDrawerOpen, setProductDrawerOpen] = useState(false);
  const [editingProduct, setEditingProduct] = useState<ProductInfo | null>(null);
  const [productSearch, setProductSearch] = useState('');
  const [manualForm] = Form.useForm();
  const [platformForm] = Form.useForm();
  const [platformDrawerOpen, setPlatformDrawerOpen] = useState(false);
  const [editingPlatform, setEditingPlatform] = useState<SourcePlatform | null>(null);

  const handleCreateProduct = async (values: Record<string, unknown>) => {
    try {
      if (editingProduct) {
        const payload: Record<string, unknown> = { ...values };
        if (Array.isArray(payload.benefits) && payload.benefits.length === 0) {
          delete payload.benefits;
        }
        await updateProduct(editingProduct.id, payload);
        message.success('产品已更新');
      } else {
        await createProduct(values as any);
        message.success('产品已创建');
      }
      setProductDrawerOpen(false);
      setEditingProduct(null);
      productForm.resetFields();
      await load();
    } catch {
      message.error('操作失败');
    }
  };

  const handleDeleteProduct = async (id: number) => {
    try {
      await deleteProduct(id);
      message.success('产品已删除');
      await load();
    } catch {
      message.error('删除失败');
    }
  };

  const openProductDrawer = async (row?: ProductInfo) => {
    setEditingProduct(row ?? null);
    if (!row) {
      productForm.resetFields();
      setProductDrawerOpen(true);
      return;
    }
    try {
      const detail = await fetchProductDetail(row.id) as {
        product: ProductInfo;
        rule: Record<string, unknown> | null;
        benefits: Array<Record<string, unknown>>;
      };
      const values: Record<string, unknown> = { ...row };
      if (detail.rule) values.rule = detail.rule;
      if (detail.benefits?.length) values.benefits = detail.benefits;
      productForm.setFieldsValue(values);
    } catch {
      productForm.setFieldsValue(row);
    }
    setProductDrawerOpen(true);
  };

  const handleCreatePlatform = async (values: Record<string, unknown>) => {
    try {
      if (editingPlatform) {
        await updatePlatform(editingPlatform.id, values as any);
        message.success('平台已更新');
      } else {
        await createPlatform(values as any);
        message.success('平台已创建');
      }
      setPlatformDrawerOpen(false);
      setEditingPlatform(null);
      platformForm.resetFields();
      await load();
    } catch {
      message.error('操作失败');
    }
  };

  const handleDeletePlatform = async (id: number) => {
    try {
      await deletePlatform(id);
      message.success('平台已删除');
      await load();
    } catch {
      message.error('删除失败');
    }
  };

  const handleManualExtraction = async (values: Record<string, unknown>) => {
    try {
      await createManualExtraction({
        source_page_id: values.source_page_id as number,
        text: values.text as string,
        html: values.html as string | undefined,
        extracted_data: JSON.parse(values.extracted_data as string),
        confidence: values.confidence as number | undefined,
      });
      message.success('手动录入已提交，请等待审核');
      manualForm.resetFields();
    } catch {
      message.error('提交失败，请检查数据格式');
    }
  };

  const load = async () => {
    setLoading(true);
    try {
      const result = await fetchProducts(undefined, productPage, productPageSize, productSearch || undefined);
      setProducts(result.products);
      setProductTotal(result.total);
      const [ingestionStatus, sourcePlatforms, pages, crawlJobs, crawlRuns, tasks] = await Promise.all([
        fetchIngestionStatus(),
        fetchSourcePlatforms(),
        fetchSourcePages(),
        fetchCrawlJobs(),
        fetchCrawlRuns(),
        fetchReviewTasks(),
      ]);
      setStatus(ingestionStatus);
      setPlatforms(sourcePlatforms);
      setSourcePages(pages);
      setJobs(crawlJobs);
      setRuns(crawlRuns);
      setReviewTasks(tasks);
    } catch {
      message.error('产品列表加载失败，请稍后重试');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => { load(); }, [productPage, productPageSize, productSearch]);

  const columns: ColumnsType<ProductInfo> = [
    { title: 'ID', dataIndex: 'id', key: 'id', width: 60 },
    { title: '产品名称', dataIndex: 'name', key: 'name' },
    { title: '公司', dataIndex: 'company', key: 'company', width: 150 },
    { title: '险种', dataIndex: 'type', key: 'type', width: 100 },
    {
      title: '状态', dataIndex: 'status', key: 'status', width: 80,
      render: (v: number) => v === 1 ? '在售' : '停售',
    },
    { title: '最低保费', dataIndex: 'premium_min', key: 'premium_min', width: 100 },
    { title: '最高保额', dataIndex: 'sum_insured_max', key: 'sum_insured_max', width: 100 },
    {
      title: '操作', key: 'action', width: 180,
      render: (_, row) => <Space>
        <Button size="small" onClick={() => openProductDrawer(row)}>编辑</Button>
        <Popconfirm title="确认删除该产品？" onConfirm={() => handleDeleteProduct(row.id)}>
          <Button size="small" danger>删除</Button>
        </Popconfirm>
      </Space>,
    },
  ];

  const platformColumns: ColumnsType<SourcePlatform> = [
    { title: 'ID', dataIndex: 'id', key: 'id', width: 60 },
    { title: '平台', dataIndex: 'name', key: 'name' },
    { title: '类型', dataIndex: 'platform_type', key: 'platform_type', width: 120 },
    { title: '基础 URL', dataIndex: 'base_url', key: 'base_url' },
    { title: '限速秒数', dataIndex: 'rate_limit_seconds', key: 'rate_limit_seconds', width: 100 },
    {
      title: '操作', key: 'action', width: 180,
      render: (_, row) => <Space>
        <Button size="small" onClick={() => {
          setEditingPlatform(row);
          platformForm.setFieldsValue(row);
          setPlatformDrawerOpen(true);
        }}>编辑</Button>
        <Popconfirm title="确认删除该平台？" onConfirm={() => handleDeletePlatform(row.id)}>
          <Button size="small" danger>删除</Button>
        </Popconfirm>
      </Space>,
    },
  ];

  const jobColumns: ColumnsType<CrawlJob> = [
    { title: 'ID', dataIndex: 'id', key: 'id', width: 60 },
    { title: '任务名称', dataIndex: 'name', key: 'name' },
    { title: '页面 ID', dataIndex: 'source_page_id', key: 'source_page_id', width: 100 },
    { title: '状态', dataIndex: 'status', key: 'status', width: 100 },
    {
      title: '操作', key: 'action', width: 120,
      render: (_, row) => <Button size="small" loading={runningJobId === row.id} onClick={async () => {
        setRunningJobId(row.id);
        try {
          const run = await runCrawlJob(row.id);
          message.success(`运行完成：${run.status}`);
          await load();
        } catch {
          message.error('运行抓取任务失败，请检查权限、robots 或抓取环境');
        } finally {
          setRunningJobId(null);
        }
      }}>运行</Button>,
    },
  ];

  const pageColumns: ColumnsType<SourcePage> = [
    { title: 'ID', dataIndex: 'id', key: 'id', width: 60 },
    { title: '平台 ID', dataIndex: 'platform_id', key: 'platform_id', width: 90 },
    { title: '类型', dataIndex: 'page_type', key: 'page_type', width: 100 },
    { title: 'URL', dataIndex: 'url', key: 'url' },
    { title: '上次抓取', dataIndex: 'last_crawled_at', key: 'last_crawled_at', width: 180 },
  ];

  const runColumns: ColumnsType<CrawlRun> = [
    { title: 'ID', dataIndex: 'id', key: 'id', width: 60 },
    { title: '任务 ID', dataIndex: 'crawl_job_id', key: 'crawl_job_id', width: 90 },
    { title: '状态', dataIndex: 'status', key: 'status', width: 100 },
    { title: 'HTTP', dataIndex: 'http_status', key: 'http_status', width: 80 },
    { title: 'Raw ID', dataIndex: 'raw_document_id', key: 'raw_document_id', width: 90 },
    { title: '错误', dataIndex: 'error_message', key: 'error_message' },
    { title: '结束时间', dataIndex: 'finished_at', key: 'finished_at', width: 180 },
  ];

  const reviewColumns: ColumnsType<ReviewTask> = [
    { title: 'ID', dataIndex: 'id', key: 'id', width: 60 },
    { title: '草稿 ID', dataIndex: 'product_draft_id', key: 'product_draft_id', width: 100 },
    { title: '产品', dataIndex: 'draft_name', key: 'draft_name' },
    { title: '险种', dataIndex: 'draft_type', key: 'draft_type', width: 100 },
    { title: '置信度', dataIndex: 'confidence', key: 'confidence', width: 90, render: (v?: number) => v == null ? '-' : v.toFixed(2) },
    { title: '状态', dataIndex: 'status', key: 'status', width: 100 },
    { title: '创建时间', dataIndex: 'created_at', key: 'created_at' },
    {
      title: '操作', key: 'action', width: 220,
      render: (_, row) => <Space>
        <Button size="small" onClick={async () => setReviewDetail(await fetchReviewTaskDetail(row.id))}>详情</Button>
        <Button size="small" type="primary" disabled={row.status !== 'pending'} onClick={async () => { await approveReviewTask(row.id, '后台审核通过'); message.success('已通过'); await load(); }}>通过</Button>
        <Button size="small" danger disabled={row.status !== 'pending'} onClick={async () => { await rejectReviewTask(row.id, '后台审核拒绝'); message.success('已拒绝'); await load(); }}>拒绝</Button>
      </Space>,
    },
  ];

  return (
    <Card style={{ maxWidth: 960, margin: '24px auto' }}>
      <Title level={3}>产品管理</Title>
      <Alert
        type="warning"
        showIcon
        style={{ marginBottom: 16 }}
        message="权限保护已启用"
        description="管理接口需要登录用户具备 crawl:read / crawl:trigger 权限。"
      />
      <Button type="primary" style={{ marginBottom: 16 }}
        onClick={async () => {
          try {
            await apiClient.post('/admin/crawl');
            message.success('爬虫任务已提交');
          } catch {
            message.error('爬虫任务提交失败，请检查权限或服务状态');
          }
        }}>
        手动触发爬虫
      </Button>
      <Tabs
        items={[
          {
            key: 'products',
            label: '产品管理',
            children: (<Space direction="vertical" style={{ width: '100%' }}>
              <Space>
              <Input.Search className="admin-search" placeholder="搜索产品名称或公司" allowClear onSearch={setProductSearch} style={{ width: 300 }} />
              <Button type="primary" onClick={() => { setEditingProduct(null); productForm.resetFields(); setProductDrawerOpen(true); }}>新增产品</Button>
            </Space>
              <Table columns={columns} dataSource={products} rowKey="id" loading={loading} size="small" scroll={{ x: 800 }} pagination={{ current: productPage, pageSize: productPageSize, total: productTotal, showSizeChanger: true, onChange: (page, pageSize) => { setProductPage(page); setProductPageSize(pageSize); } }} />
            </Space>),
          },
          {
            key: 'ingestion',
            label: '数据采集',
            children: (
              <div>
                <Row gutter={12} style={{ marginBottom: 16 }}>
                  <Col xs={8} sm={4}><Statistic title="平台" value={status?.source_platforms || 0} /></Col>
                  <Col xs={8} sm={4}><Statistic title="页面" value={status?.source_pages || 0} /></Col>
                  <Col xs={8} sm={4}><Statistic title="任务" value={status?.crawl_jobs || 0} /></Col>
                  <Col xs={8} sm={4}><Statistic title="运行" value={status?.crawl_runs || 0} /></Col>
                  <Col xs={8} sm={4}><Statistic title="草稿" value={status?.product_drafts || 0} /></Col>
                  <Col xs={8} sm={4}><Statistic title="审核" value={status?.review_tasks || 0} /></Col>
                </Row>
                <Card size="small" title="数据源平台" style={{ marginBottom: 16 }}>
                  <Space style={{ marginBottom: 8 }}>
                  <Button type="primary" onClick={() => { setEditingPlatform(null); platformForm.resetFields(); setPlatformDrawerOpen(true); }}>新增平台</Button>
                </Space>
                <Table columns={platformColumns} dataSource={platforms} rowKey="id" loading={loading} size="small" pagination={false} />
                </Card>
                <Card size="small" title="新增数据源页面" style={{ marginBottom: 16 }}>
                  <Form form={sourcePageForm} layout="inline" onFinish={async (values) => {
                    await createSourcePage(values);
                    sourcePageForm.resetFields();
                    message.success('数据源页面已创建');
                    await load();
                  }}>
                    <Form.Item name="platform_id" rules={[{ required: true }]}><InputNumber placeholder="平台 ID" min={1} /></Form.Item>
                    <Form.Item name="url" rules={[{ required: true, type: 'url' }]} style={{ minWidth: 360 }}><Input placeholder="产品页 URL" /></Form.Item>
                    <Form.Item name="page_type" initialValue="product"><Input placeholder="页面类型" /></Form.Item>
                    <Button type="primary" htmlType="submit">新增页面</Button>
                  </Form>
                </Card>
                <Card size="small" title="数据源页面" style={{ marginBottom: 16 }}>
                  <Table columns={pageColumns} dataSource={sourcePages} rowKey="id" loading={loading} size="small" pagination={false} />
                </Card>
                <Card size="small" title="新增抓取任务" style={{ marginBottom: 16 }}>
                  <Form form={jobForm} layout="inline" onFinish={async (values) => {
                    await createCrawlJob(values);
                    jobForm.resetFields();
                    message.success('抓取任务已创建');
                    await load();
                  }}>
                    <Form.Item name="name" rules={[{ required: true }]}><Input placeholder="任务名称" /></Form.Item>
                    <Form.Item name="source_page_id" rules={[{ required: true }]}><InputNumber placeholder="页面 ID" min={1} /></Form.Item>
                    <Button type="primary" htmlType="submit">新增任务</Button>
                  </Form>
                </Card>
                <Card size="small" title="抓取任务" style={{ marginBottom: 16 }}>
                  <Table columns={jobColumns} dataSource={jobs} rowKey="id" loading={loading} size="small" pagination={false} />
                </Card>
                <Card size="small" title="运行日志" style={{ marginBottom: 16 }}>
                  <Table columns={runColumns} dataSource={runs} rowKey="id" loading={loading} size="small" pagination={false} />
                </Card>
                <Card size="small" title="审核队列">
                  <Table columns={reviewColumns} dataSource={reviewTasks} rowKey="id" loading={loading} size="small" pagination={false} />
                </Card>
              </div>
            ),
          },
          {
            key: 'manual',
            label: '手动录入',
            children: (
              <Card size="small" title="手动录入产品数据">
                <Form
                  form={manualForm}
                  layout="vertical"
                  onFinish={handleManualExtraction}
                >
                  <Form.Item name="source_page_id" label="数据源页面 ID" rules={[{ required: true }]}>
                    <InputNumber placeholder="输入页面 ID" min={1} style={{ width: '100%' }} />
                  </Form.Item>
                  <Form.Item name="text" label="文本内容" rules={[{ required: true }]}>
                    <Input.TextArea rows={4} placeholder="输入产品文本内容" />
                  </Form.Item>
                  <Form.Item name="html" label="HTML 内容（可选）">
                    <Input.TextArea rows={4} placeholder="输入原始 HTML" />
                  </Form.Item>
                  <Form.Item name="extracted_data" label="提取数据（JSON 格式）" rules={[{ required: true }]}>
                    <Input.TextArea rows={6} placeholder='{"name": "产品名", "company": "公司名", "type": "医疗险"}' />
                  </Form.Item>
                  <Form.Item name="confidence" label="置信度" initialValue={0.5}>
                    <InputNumber min={0} max={1} step={0.1} style={{ width: '100%' }} />
                  </Form.Item>
                  <Button type="primary" htmlType="submit">提交录入</Button>
                </Form>
              </Card>
            ),
          },
        ]}
      />
      <Drawer
        title={editingProduct ? '编辑产品' : '新增产品'}
        width="min(600px, 100vw)"
        open={productDrawerOpen}
        onClose={() => { setProductDrawerOpen(false); setEditingProduct(null); }}
        footer={null}
      >
        <Form
          form={productForm}
          layout="vertical"
          onFinish={handleCreateProduct}
        >
          <Form.Item name="name" label="产品名称" rules={[{ required: true }]}>
            <Input placeholder="如：平安福终身寿险" />
          </Form.Item>
          <Form.Item name="company" label="保险公司" rules={[{ required: true }]}>
            <Input placeholder="如：中国平安" />
          </Form.Item>
          <Form.Item name="type" label="险种" rules={[{ required: true }]}>
            <Select placeholder="选择险种">
              <Select.Option value="医疗险">医疗险</Select.Option>
              <Select.Option value="意外险">意外险</Select.Option>
              <Select.Option value="重疾险">重疾险</Select.Option>
              <Select.Option value="定期寿险">定期寿险</Select.Option>
              <Select.Option value="防癌险">防癌险</Select.Option>
              <Select.Option value="年金险">年金险</Select.Option>
            </Select>
          </Form.Item>
          <Row gutter={16}>
            <Col span={12}>
              <Form.Item name="premium_min" label="最低保费">
                <InputNumber min={0} style={{ width: '100%' }} />
              </Form.Item>
            </Col>
            <Col span={12}>
              <Form.Item name="premium_max" label="最高保费">
                <InputNumber min={0} style={{ width: '100%' }} />
              </Form.Item>
            </Col>
          </Row>
          <Row gutter={16}>
            <Col span={12}>
              <Form.Item name="sum_insured_min" label="最低保额">
                <InputNumber min={0} style={{ width: '100%' }} />
              </Form.Item>
            </Col>
            <Col span={12}>
              <Form.Item name="sum_insured_max" label="最高保额">
                <InputNumber min={0} style={{ width: '100%' }} />
              </Form.Item>
            </Col>
          </Row>
          <Form.Item name="source_url" label="来源URL">
            <Input placeholder="https://example.com" />
          </Form.Item>
          <Form.Item name="deductible" label="免赔额">
            <InputNumber min={0} style={{ width: '100%' }} />
          </Form.Item>
          <Divider orientation="left" plain>投保规则（Rule）</Divider>
          <Row gutter={16}>
            <Col span={12}>
              <Form.Item name={['rule', 'min_age']} label="最小投保年龄" initialValue={0}>
                <InputNumber min={0} max={120} style={{ width: '100%' }} />
              </Form.Item>
            </Col>
            <Col span={12}>
              <Form.Item name={['rule', 'max_age']} label="最大投保年龄" initialValue={100}>
                <InputNumber min={0} max={120} style={{ width: '100%' }} />
              </Form.Item>
            </Col>
          </Row>
          <Row gutter={16}>
            <Col span={12}>
              <Form.Item name={['rule', 'job_class_limit']} label="职业等级上限" initialValue={6}>
                <InputNumber min={1} max={6} style={{ width: '100%' }} />
              </Form.Item>
            </Col>
            <Col span={12}>
              <Form.Item name={['rule', 'waiting_period_days']} label="等待期(天)" initialValue={90}>
                <InputNumber min={0} style={{ width: '100%' }} />
              </Form.Item>
            </Col>
          </Row>
          <Form.Item name={['rule', 'has_insured_waiver']} label="被保险人豁免" valuePropName="checked" initialValue={false}>
            <Switch />
          </Form.Item>
          <Form.Item name={['rule', 'has_insurer_waiver']} label="保险人豁免" valuePropName="checked" initialValue={false}>
            <Switch />
          </Form.Item>
          <Divider orientation="left" plain>保障责任（Benefit）</Divider>
          <Form.List name="benefits">
            {(fields, { add, remove }) => (
              <>
                {fields.map(({ key, name, ...restField }) => (
                  <Space className="benefit-row" key={key} style={{ display: 'flex', marginBottom: 8 }} align="baseline">
                    <Form.Item {...restField} name={[name, 'benefit_name']} rules={[{ required: true, message: '责任名称必填' }]}>
                      <Input placeholder="责任名称" style={{ width: 140 }} />
                    </Form.Item>
                    <Form.Item {...restField} name={[name, 'benefit_type']}>
                      <Select placeholder="类型" style={{ width: 100 }} options={[
                        { value: 'basic', label: '基本' },
                        { value: 'special', label: '特别' },
                      ]} />
                    </Form.Item>
                    <Form.Item {...restField} name={[name, 'benefit_amount']}>
                      <Input placeholder="保额/金额" style={{ width: 120 }} />
                    </Form.Item>
                    <Form.Item {...restField} name={[name, 'payment_limit']}>
                      <Input placeholder="给付限额" style={{ width: 120 }} />
                    </Form.Item>
                    <Button type="text" danger onClick={() => remove(name)}>删除</Button>
                  </Space>
                ))}
                <Button type="dashed" onClick={() => add({ benefit_type: 'basic' })} block style={{ marginBottom: 8 }}>添加责任</Button>
              </>
            )}
          </Form.List>
          <Button type="primary" htmlType="submit">保存</Button>
        </Form>
      </Drawer>
      <Drawer
        title={editingPlatform ? '编辑平台' : '新增平台'}
        width="min(520px, 100vw)"
        open={platformDrawerOpen}
        onClose={() => { setPlatformDrawerOpen(false); setEditingPlatform(null); }}
        footer={null}
      >
        <Form
          form={platformForm}
          layout="vertical"
          onFinish={handleCreatePlatform}
        >
          <Form.Item name="name" label="平台名称" rules={[{ required: true }]}>
            <Input placeholder="如：中国保险协会" />
          </Form.Item>
          <Form.Item name="platform_type" label="平台类型" initialValue="third_party">
            <Input placeholder="third_party / official / aggregator" />
          </Form.Item>
          <Form.Item name="base_url" label="基础 URL">
            <Input placeholder="https://example.com" />
          </Form.Item>
          <Form.Item name="robots_url" label="Robots URL">
            <Input placeholder="https://example.com/robots.txt" />
          </Form.Item>
          <Form.Item name="rate_limit_seconds" label="限速秒数" initialValue={1}>
            <InputNumber min={0} style={{ width: '100%' }} />
          </Form.Item>
          <Form.Item name="is_active" label="是否激活" initialValue={1} valuePropName="checked">
            <input type="checkbox" />
          </Form.Item>
          <Button type="primary" htmlType="submit">保存</Button>
        </Form>
      </Drawer>
      <Drawer title="审核详情" width="min(720px, 100vw)" open={!!reviewDetail} onClose={() => setReviewDetail(null)}>
        {reviewDetail && <Space direction="vertical" style={{ width: '100%' }} size="middle">
          <Alert type="info" showIcon message={`状态：${reviewDetail.status}，置信度：${reviewDetail.confidence?.toFixed(2) ?? '-'}`} />
          <Card size="small" title="抽取草稿"><pre style={{ whiteSpace: 'pre-wrap' }}>{JSON.stringify(reviewDetail.draft, null, 2)}</pre></Card>
          <Card size="small" title="字段证据">
            <Table
              rowKey={(row) => row.field_name}
              size="small"
              pagination={false}
              dataSource={reviewDetail.evidence}
              columns={[
                { title: '字段', dataIndex: 'field_name', key: 'field_name', width: 120 },
                { title: '值', dataIndex: 'field_value', key: 'field_value', width: 160 },
                { title: '证据', dataIndex: 'evidence_text', key: 'evidence_text' },
                { title: '置信度', dataIndex: 'confidence', key: 'confidence', width: 90, render: (v: number) => v.toFixed(2) },
              ]}
            />
          </Card>
        </Space>}
      </Drawer>
    </Card>
  );
}
