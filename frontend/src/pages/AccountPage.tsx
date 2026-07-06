import { useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { Button, Card, Descriptions, List, Space, Tag, Typography, message } from 'antd';
import { fetchMe, fetchMyProfiles, fetchMyRecommendations, getStoredUser, logout } from '../api/auth';
import type { AuthUser, RecommendationRecord, SavedProfile } from '../types';

const { Text, Title } = Typography;

export default function AccountPage() {
  const [user, setUser] = useState<AuthUser | null>(() => getStoredUser());
  const [records, setRecords] = useState<RecommendationRecord[]>([]);
  const [profiles, setProfiles] = useState<SavedProfile[]>([]);
  const [loading, setLoading] = useState(false);
  const navigate = useNavigate();

  useEffect(() => {
    const load = async () => {
      setLoading(true);
      try {
        const [me, recommendationRecords, savedProfiles] = await Promise.all([
          fetchMe(),
          fetchMyRecommendations(),
          fetchMyProfiles(),
        ]);
        setUser(me);
        setRecords(recommendationRecords);
        setProfiles(savedProfiles);
      } catch {
        message.error('账号信息加载失败，请重新登录');
      } finally {
        setLoading(false);
      }
    };
    load();
  }, []);

  if (!user) return null;

  return (
    <Space direction="vertical" size="large" style={{ width: '100%', maxWidth: 900, margin: '24px auto' }}>
      <Card loading={loading}>
        <Space style={{ width: '100%', justifyContent: 'space-between' }} align="start">
          <div>
            <Title level={3}>我的账号</Title>
            <Text type="secondary">查看登录身份、权限和已保存的推荐数据。</Text>
          </div>
          <Button onClick={async () => {
            await logout();
            navigate('/login', { replace: true });
          }}>退出登录</Button>
        </Space>
        <Descriptions bordered size="small" column={1} style={{ marginTop: 24 }}>
          <Descriptions.Item label="邮箱">{user.email}</Descriptions.Item>
          <Descriptions.Item label="姓名">{user.full_name || '-'}</Descriptions.Item>
          <Descriptions.Item label="角色">
            {user.roles.map((role) => <Tag key={role}>{role}</Tag>)}
          </Descriptions.Item>
          <Descriptions.Item label="权限">
            {user.permissions.map((permission) => <Tag key={permission} color="blue">{permission}</Tag>)}
          </Descriptions.Item>
        </Descriptions>
      </Card>

      <Card title="推荐历史">
        <List
          dataSource={records}
          locale={{ emptyText: '暂无推荐历史。登录后提交推荐会自动保存。' }}
          renderItem={(record) => (
            <List.Item>
              <List.Item.Meta
                title={`推荐记录 #${record.id}`}
                description={record.created_at ? new Date(record.created_at).toLocaleString() : '-'}
              />
            </List.Item>
          )}
        />
      </Card>

      <Card title="保存的画像">
        <List
          dataSource={profiles}
          locale={{ emptyText: '暂无保存画像。' }}
          renderItem={(profile) => (
            <List.Item>
              <List.Item.Meta
                title={profile.name}
                description={profile.created_at ? new Date(profile.created_at).toLocaleString() : '-'}
              />
            </List.Item>
          )}
        />
      </Card>
    </Space>
  );
}
