import { useEffect, useState } from 'react';
import { useNavigate, Link, useLocation } from 'react-router-dom';
import { Alert, Button, Card, Descriptions, Input, List, Modal, Popconfirm, Space, Tag, Typography, message } from 'antd';
import { deleteProfile, deleteRecommendation, fetchMe, fetchMyProfiles, fetchMyRecommendations, fetchProfileDetail, getStoredUser, logout, saveProfile, updateProfile } from '../api/auth';
import type { AuthUser, RecommendationRecord, SavedProfile, UserProfile } from '../types';
import { useI18n } from '../i18n';

const { Text, Title } = Typography;

export default function AccountPage() {
  const { t } = useI18n();
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
      await saveProfile(saveName.trim() || t('common.unnamedProfile'), currentProfile as unknown as Record<string, unknown>);
      setSaveModalOpen(false);
      setSaveName('');
      message.success(t('account.saveOk'));
      const savedProfiles = await fetchMyProfiles();
      setProfiles(savedProfiles);
    } catch {
      message.error(t('account.saveFailed'));
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
        message.error(t('account.loadFailed'));
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
      message.success(t('account.recordDeleted'));
    } catch {
      message.error(t('account.deleteFailed'));
    }
  };

  const handleDeleteProfile = async (id: number) => {
    try {
      await deleteProfile(id);
      setProfiles(profiles.filter(p => p.id !== id));
      message.success(t('account.profileDeleted'));
    } catch {
      message.error(t('account.deleteFailed'));
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
      message.success(t('account.profileUpdated'));
      setEditModalOpen(false);
      setEditingProfile(null);
    } catch {
      message.error(t('account.updateFailed'));
    }
  };

  if (!user) return null;

  return (
    <Space direction="vertical" size="large" style={{ width: '100%', margin: '0 auto' }}>
      <Card loading={loading}>
        <Space style={{ width: '100%', justifyContent: 'space-between' }} align="start">
          <div>
            <Title level={3}>{t('account.title')}</Title>
            <Text type="secondary">{t('account.subtitle')}</Text>
          </div>
          <Button onClick={async () => {
            await logout();
            navigate('/login', { replace: true });
          }}>{t('account.logout')}</Button>
        </Space>
        <Descriptions bordered size="small" column={1} style={{ marginTop: 24 }}>
          <Descriptions.Item label={t('account.email')}>{user.email}</Descriptions.Item>
          <Descriptions.Item label={t('account.fullName')}>{user.full_name || '-'}</Descriptions.Item>
          <Descriptions.Item label={t('account.roles')}>
            {user.roles.map((role) => <Tag key={role}>{role}</Tag>)}
          </Descriptions.Item>
          <Descriptions.Item label={t('account.permissions')}>
            {user.permissions.map((permission) => <Tag key={permission} color="blue">{permission}</Tag>)}
          </Descriptions.Item>
        </Descriptions>
      </Card>

      <Card title={t('account.history')}>
        <List
          dataSource={records}
          locale={{ emptyText: t('account.historyEmpty') }}
          renderItem={(record) => (
            <List.Item
              actions={[
                <Link key="view" to={`/result?recordId=${record.id}`}>{t('account.viewResult')}</Link>,
                <Popconfirm key="delete" title={t('account.deleteRecordConfirm')} description={t('account.deleteIrreversible')} onConfirm={() => handleDeleteRecord(record.id)}>
                  <Button type="link" size="small" danger>{t('common.delete')}</Button>
                </Popconfirm>,
              ]}
            >
              <List.Item.Meta
                title={t('account.recordTitle', { id: record.id })}
                description={record.created_at ? new Date(record.created_at).toLocaleString() : '-'}
              />
            </List.Item>
          )}
        />
      </Card>

      <Card title={t('account.profiles')}>
        <Space style={{ width: '100%', justifyContent: 'flex-end', marginBottom: 8 }}>
          {currentProfile ? (
            <Button type="primary" onClick={() => setSaveModalOpen(true)}>{t('account.saveCurrent')}</Button>
          ) : (
            <Text type="secondary" style={{ fontSize: 12 }}>{t('account.saveHint')}</Text>
          )}
        </Space>
        <List
          dataSource={profiles}
          locale={{ emptyText: t('account.profilesEmpty') }}
          renderItem={(profile) => (
            <List.Item
              actions={[
                <Button key="load" type="link" size="small" onClick={async () => {
                  try {
                    const detail = await fetchProfileDetail(profile.id);
                    navigate(`/?profileId=${profile.id}`, { state: { profile: detail.profile } });
                  } catch {
                    message.error(t('account.loadProfileFailed'));
                  }
                }}>{t('account.loadToForm')}</Button>,
                <Button key="edit" type="link" size="small" onClick={() => handleEditProfile(profile)}>{t('common.edit')}</Button>,
                <Popconfirm key="delete" title={t('account.deleteProfileConfirm')} description={t('account.deleteIrreversible')} onConfirm={() => handleDeleteProfile(profile.id)}>
                  <Button type="link" size="small" danger>{t('common.delete')}</Button>
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
        title={t('common.saveHealthProfile')}
        open={saveModalOpen}
        onOk={handleSaveCurrentProfile}
        onCancel={() => { setSaveModalOpen(false); setSaveName(''); }}
        okText={t('common.save')}
        confirmLoading={saving}
      >
        <Space direction="vertical" style={{ width: '100%' }}>
          <Alert
            type="info"
            showIcon
            message={t('common.privacyTitle')}
            description={t('account.privacyBody')}
          />
          <div>
            <Text strong>{t('common.profileName')}</Text>
            <Input
              placeholder={t('common.profilePlaceholder')}
              value={saveName}
              onChange={(e) => setSaveName(e.target.value)}
              maxLength={120}
            />
          </div>
        </Space>
      </Modal>
      <Modal
        title={t('account.editTitle')}
        open={editModalOpen}
        onOk={handleSaveEdit}
        onCancel={() => { setEditModalOpen(false); setEditingProfile(null); }}
      >
        {editingProfile && (
          <Space direction="vertical" style={{ width: '100%' }}>
            <div>
              <Text strong>{t('common.name')}</Text>
              <Input
                value={editingProfile.name}
                onChange={(e) => setEditingProfile({ ...editingProfile, name: e.target.value })}
              />
            </div>
            <div>
              <Text strong>{t('common.note')}</Text>
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