import { Navigate, useLocation } from 'react-router-dom';
import type { ReactNode } from 'react';
import { getStoredUser } from '../api/auth';

interface Props {
  children: ReactNode;
  permission?: string;
}

export default function ProtectedRoute({ children, permission }: Props) {
  const location = useLocation();
  const user = getStoredUser();

  if (!user) {
    return <Navigate to="/login" replace state={{ from: location }} />;
  }

  if (permission && !user.permissions.includes(permission)) {
    return <Navigate to="/account" replace />;
  }

  return <>{children}</>;
}
