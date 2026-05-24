import { useState, useEffect } from 'react';
import { Table, Button, Card, Typography, message } from 'antd';
import { fetchProducts } from '../api/products';
import type { ProductInfo } from '../types';
import type { ColumnsType } from 'antd/es/table';

const { Title } = Typography;

export default function AdminPage() {
  const [products, setProducts] = useState<ProductInfo[]>([]);
  const [loading, setLoading] = useState(false);

  const load = async () => {
    setLoading(true);
    const data = await fetchProducts();
    setProducts(data);
    setLoading(false);
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

  return (
    <Card style={{ maxWidth: 960, margin: '24px auto' }}>
      <Title level={3}>产品管理</Title>
      <Button type="primary" style={{ marginBottom: 16 }}
        onClick={async () => {
          await fetch('/api/admin/crawl', { method: 'POST' });
          message.success('爬虫任务已提交');
        }}>
        手动触发爬虫
      </Button>
      <Table columns={columns} dataSource={products} rowKey="id"
        loading={loading} size="small" pagination={{ pageSize: 20 }} />
    </Card>
  );
}
