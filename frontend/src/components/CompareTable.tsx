import { Table, Tag } from 'antd';
import type { ColumnsType } from 'antd/es/table';
import type { ProductItem } from '../types';

interface Props {
  products: ProductItem[];
}

export default function CompareTable({ products }: Props) {
  if (!products.length) return null;

  const columns: ColumnsType<ProductItem> = [
    {
      title: '产品名称', dataIndex: 'name', key: 'name', fixed: 'left', width: 200,
      render: (v: string, record: ProductItem) =>
        record.source_url ? (
          <a href={record.source_url} target="_blank" rel="noopener noreferrer">{v}</a>
        ) : v,
    },
    { title: '保险公司', dataIndex: 'company', key: 'company', width: 120 },
    {
      title: '险种', dataIndex: 'type', key: 'type', width: 100,
      render: (v: string) => <Tag>{v}</Tag>,
    },
    {
      title: '保费(元/年)', dataIndex: 'premium', key: 'premium', width: 120,
      render: (v: number) => `¥${v.toLocaleString()}`,
      sorter: (a: ProductItem, b: ProductItem) => a.premium - b.premium,
    },
    {
      title: '保额', dataIndex: 'sum_insured', key: 'sum_insured', width: 120,
      render: (v: number) => v.toLocaleString(),
    },
    {
      title: '综合评分', dataIndex: 'score', key: 'score', width: 100,
      render: (v: number) => <Tag color={v >= 80 ? 'green' : v >= 60 ? 'orange' : 'red'}>{v}</Tag>,
      sorter: (a: ProductItem, b: ProductItem) => a.score - b.score,
    },
    { title: '保障全面性', dataIndex: ['score_detail', 'coverage'], key: 'coverage', width: 100 },
    { title: '保费竞争力', dataIndex: ['score_detail', 'price'], key: 'price', width: 100 },
    { title: '投保宽松度', dataIndex: ['score_detail', 'flexibility'], key: 'flexibility', width: 100 },
  ];

  return (
    <Table
      columns={columns}
      dataSource={products}
      rowKey="id"
      scroll={{ x: 1100 }}
      pagination={false}
      size="small"
      bordered
    />
  );
}
