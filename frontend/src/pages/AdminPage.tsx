import { useState, useEffect } from 'react';
import { Alert, Button, Card, Col, Drawer, Form, Input, InputNumber, Row, Space, Statistic, Table, Tabs, Typography, message } from 'antd';
import apiClient from '../api/client';
import { fetchProducts } from '../api/products';
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

  const load = async () => {
    setLoading(true);
    try {
      const data = await fetchProducts();
      setProducts(data);
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

  useEffect(() => { load(); }, []);

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
  ];

  const platformColumns: ColumnsType<SourcePlatform> = [
    { title: 'ID', dataIndex: 'id', key: 'id', width: 60 },
    { title: '平台', dataIndex: 'name', key: 'name' },
    { title: '类型', dataIndex: 'platform_type', key: 'platform_type', width: 120 },
    { title: '基础 URL', dataIndex: 'base_url', key: 'base_url' },
    { title: '限速秒数', dataIndex: 'rate_limit_seconds', key: 'rate_limit_seconds', width: 100 },
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
            children: <Table columns={columns} dataSource={products} rowKey="id" loading={loading} size="small" pagination={{ pageSize: 20 }} />,
          },
          {
            key: 'ingestion',
            label: '数据采集',
            children: (
              <div>
                <Row gutter={12} style={{ marginBottom: 16 }}>
                  <Col span={4}><Statistic title="平台" value={status?.source_platforms || 0} /></Col>
                  <Col span={4}><Statistic title="页面" value={status?.source_pages || 0} /></Col>
                  <Col span={4}><Statistic title="任务" value={status?.crawl_jobs || 0} /></Col>
                  <Col span={4}><Statistic title="运行" value={status?.crawl_runs || 0} /></Col>
                  <Col span={4}><Statistic title="草稿" value={status?.product_drafts || 0} /></Col>
                  <Col span={4}><Statistic title="审核" value={status?.review_tasks || 0} /></Col>
                </Row>
                <Card size="small" title="数据源平台" style={{ marginBottom: 16 }}>
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
        ]}
      />
      <Drawer title="审核详情" width={720} open={!!reviewDetail} onClose={() => setReviewDetail(null)}>
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
