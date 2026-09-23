import React, { useEffect, useState } from 'react';
import { Alert } from 'antd';
import { isManagementLoginRequired, subscribeManagementSession } from './shared/managementSession';

export default function ManagementSessionNotice() {
  const [loginRequired, setLoginRequired] = useState(isManagementLoginRequired);
  useEffect(() => {
    const update = () => setLoginRequired(isManagementLoginRequired());
    const unsubscribe = subscribeManagementSession(update);
    update(); // Also observe a 401 returned before this effect subscribed.
    return unsubscribe;
  }, []);
  return loginRequired ? <Alert type="warning" showIcon role="alert"
    message="尚未登录或登录已过期"
    description={<>请先保留未保存内容，再<a href="/login">前往登录</a>。失败的操作不会自动重试。</>}
  /> : null;
}
