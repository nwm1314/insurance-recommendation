import { useEffect, useState } from 'react';
import { useNavigate, Link, useLocation } from 'react-router-dom';
import { Alert, Button, Card, Descriptions, Input, List, Modal, Popconfirm, Space, Tag, Typography, message } from 'antd';
import { deleteProfile, deleteRecommendation, fetchMe, fetchMyProfiles, fetchMyRecommendations, fetchProfileDetail, getStoredUser, logout, saveProfile, updateProfile } from '../api/auth';
import type { AuthUser, RecommendationRecord, SavedProfile, UserProfile } from '../types';

const { Text, Title } = Typography;

export default function AccountPage() {
  const [user, setUser] = useState<AuthUser | null>(() => getStoredUser());
  const [records, setRecords] = useState<RecommendationRecord[]>([]);
  const [profiles, setProfiles] = useState<SavedProfile[]>([]);
  const [loading, setLoading] = useState(false);
  const [editingProfile, setEditingProfile] = useState<SavedProfile | null>(null);
  const [editModalOpen, setEditModalOpen] = useState(false);
  const [saveModalOpen, setSaveModalOpen] = useState(false);
  const [saveName, setSaveName] = useState('');
  const [saving, setSaving] = useState(false);
  const navigate = useNavigate();
  const location = useLocation();
  const currentProfile = location.state?.profile as UserProfile | undefined;

  const handleSaveCurrentProfile = async () => {
    if (!currentProfile) return;
    setSaving(true);
    try {
      await saveProfile(saveName.trim() || '未命名画像', currentProfile as unknown as Record<string, unknown>);
      setSaveModalOpen(false);
      setSaveName('');
      message.success('画像已保存');
      const savedProfiles = await fetchMyProfiles();
      setProfiles(savedProfiles);
    } catch {
      message.error('画像保存失败，请稍后重试');
    } finally {
      setSaving(false);
    }
  };

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
        message.error('账户信息加载失败，请重新登录');
      } finally {
        setLoading(false);
      }
    };
    load();
  }, []);

  const handleDeleteRecord = async (id: number) => {
    try {
      await deleteRecommendation(id);
      setRecords(records.filter(r => r.id !== id));
      message.success('推荐记录已删除');
    } catch {
      message.error('删除失败');
    }
  };

  const handleDeleteProfile = async (id: number) => {
    try {
      await deleteProfile(id);
      setProfiles(profiles.filter(p => p.id !== id));
      message.success('画像已删除');
    } catch {
      message.error('删除失败');
    }
  };

  const handleEditProfile = (profile: SavedProfile) => {
    setEditingProfile(profile);
    setEditModalOpen(true);
  };

  const handleSaveEdit = async () => {
    if (!editingProfile) return;
    try {
      const updated = await updateProfile(editingProfile.id, editingProfile.name, editingProfile.profile, editingProfile.note || undefined);
      setProfiles(profiles.map(p => p.id === updated.id ? updated : p));
      message.success('画像已更新');
      setEditModalOpen(false);
      setEditingProfile(null);
    } catch {
      message.error('更新失败');
    }
  };

  if (!user) return null;

  return (
    <Space direction="vertical" size="large" style={{ width: '100%', margin: '0 auto' }}>
      <Card loading={loading}>
        <Space style={{ width: '100%', justifyContent: 'space-between' }} align="start">
          <div>
            <Title level={3}>我的账户</Title>
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
            <List.Item
              actions={[
                <Link key="view" to={`/result?recordId=${record.id}`}>查看结果</Link>,
                <Popconfirm key="delete" title="确认删除该推荐记录？" description="删除后不可恢复。" onConfirm={() => handleDeleteRecord(record.id)}>
                  <Button type="link" size="small" danger>删除</Button>
                </Popconfirm>,
              ]}
            >
              <List.Item.Meta
                title={`推荐记录 #${record.id}`}
                description={record.created_at ? new Date(record.created_at).toLocaleString() : '-'}
              />
            </List.Item>
          )}
        />
      </Card>

      <Card title="保存的画像">
        <Space style={{ width: '100%', justifyContent: 'flex-end', marginBottom: 8 }}>
          {currentProfile ? (
            <Button type="primary" onClick={() => setSaveModalOpen(true)}>保存当前画像</Button>
          ) : (
            <Text type="secondary" style={{ fontSize: 12 }}>在结果页点击“保存画像”可保存本次问卷；从结果页“修改信息”进入本页可保存当前画像。</Text>
          )}
        </Space>
        <List
          dataSource={profiles}
          locale={{ emptyText: '暂无保存画像。' }}
          renderItem={(profile) => (
            <List.Item
              actions={[
                <Button key="load" type="link" size="small" onClick={async () => {
                  try {
                    const detail = await fetchProfileDetail(profile.id);
                    navigate(`/?profileId=${profile.id}`, { state: { profile: detail.profile } });
                  } catch {
                    message.error('加载画像失败');
                  }
                }}>加载到表单</Button>,
                <Button key="edit" type="link" size="small" onClick={() => handleEditProfile(profile)}>编辑</Button>,
                <Popconfirm key="delete" title="确认删除该画像？" description="删除后不可恢复。" onConfirm={() => handleDeleteProfile(profile.id)}>
                  <Button type="link" size="small" danger>删除</Button>
                </Popconfirm>,
              ]}
            >
              <List.Item.Meta
                title={profile.name}
                description={profile.created_at ? new Date(profile.created_at).toLocaleString() : '-'}
              />
            </List.Item>
          )}
        />
      </Card>
      <Modal
        title="保存健康画像"
        open={saveModalOpen}
        onOk={handleSaveCurrentProfile}
        onCancel={() => { setSaveModalOpen(false); setSaveName(''); }}
        okText="保存"
        confirmLoading={saving}
      >
        <Space direction="vertical" style={{ width: '100%' }}>
          <Alert
            type="info"
            showIcon
            message="隐私提示"
            description="画像仅保存在您的账户中，仅您本人可见，不会被公开或用于其他用途；可随时在本页编辑或删除。"
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
      <Modal
        title="编辑画像"
        open={editModalOpen}
        onOk={handleSaveEdit}
        onCancel={() => { setEditModalOpen(false); setEditingProfile(null); }}
      >
        {editingProfile && (
          <Space direction="vertical" style={{ width: '100%' }}>
            <div>
              <Text strong>名称</Text>
              <Input
                value={editingProfile.name}
                onChange={(e) => setEditingProfile({ ...editingProfile, name: e.target.value })}
              />
            </div>
            <div>
              <Text strong>备注</Text>
              <Input.TextArea
                value={editingProfile.note || ''}
                onChange={(e) => setEditingProfile({ ...editingProfile, note: e.target.value })}
              />
            </div>
          </Space>
        )}
      </Modal>
    </Space>
  );
}