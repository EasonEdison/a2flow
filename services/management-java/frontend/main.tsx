import React, { lazy, Suspense } from 'react';
import { createRoot } from 'react-dom/client';
import { BrowserRouter, Link, Navigate, Route, Routes, useLocation } from 'react-router-dom';
import { Alert, Spin } from 'antd';
import { ApartmentOutlined, ApiOutlined, AppstoreOutlined, LayoutOutlined } from '@ant-design/icons';
import 'antd/dist/antd.css';
import './management.less';
import { A2UI_APPLICATION_ROUTES } from './a2uiCatalogContracts';
import ManagementSessionNotice from './ManagementSessionNotice';

const SkillPage = lazy(() => import('./index'));
const ComponentCenter = lazy(() => import('./ComponentCenterPage'));
const ComponentDetail = lazy(() => import('./ComponentAssetDetailPage'));
const ComponentAuthoring = lazy(() => import('./ComponentAssetAuthoringPage'));
const ResultPreview = lazy(() => import('./SkillResultPreviewPage'));
const Catalog = lazy(() => import('./A2uiCatalogPage'));
const Applications = lazy(() => import('./A2uiApplicationListPage'));
const ApplicationEditor = lazy(() => import('./A2uiApplicationEditorPage'));
const Capabilities = lazy(() => import('./CapabilityCenterPage'));
const CapabilityEditor = lazy(() => import('./CapabilityActionAuthoringPage'));
const Workflows = lazy(() => import('./workflow/WorkflowListPage'));
const WorkflowEditor = lazy(() => import('./workflow/WorkflowOrchestrationPage'));

const rootElement = document.getElementById('root');
if (!rootElement) throw new Error('缺少管理台 root 挂载节点');

function ManagementShell() {
  const { pathname } = useLocation();
  const currentPath = pathname.replace(/\/+$/, '');
  const isSection = (path: string) => currentPath === path || currentPath.startsWith(`${path}/`);
  const navigation = [
    { to: '/management', label: 'Skill', icon: AppstoreOutlined, active: currentPath === '/management' || currentPath === '/management/detail' },
    { to: '/management/capabilities', label: '业务能力', icon: ApiOutlined, active: isSection('/management/capabilities') },
    { to: '/management/components', label: 'A2UI / 组件', icon: LayoutOutlined, active: isSection('/management/components') },
    { to: '/management/workflows', label: 'Workflow', icon: ApartmentOutlined, active: isSection('/management/workflows') },
  ];
  return <>
    <a className="management-skip-link" href="#management-main">跳转到主内容</a>
    <header className="management-header">
      <div className="management-brand"><strong>A2Flow</strong><span>管理工作台</span></div>
      <nav className="management-navigation" aria-label="管理台导航">
        {navigation.map(({ to, label, active, icon: Icon }) => (
          <Link key={to} to={to} className={active ? 'is-current' : undefined}
            aria-current={active ? 'page' : undefined}><Icon aria-hidden="true" /><span>{label}</span></Link>
        ))}
      </nav>
      <div className="management-account-actions">
        <a href="/login">登录</a>
        <form action="/logout" method="post"><button type="submit">退出登录</button></form>
      </div>
    </header>
    <main id="management-main" className="management-content" tabIndex={-1}>
      <ManagementSessionNotice />
      <Suspense fallback={<div className="management-loading" role="status"><Spin tip="正在加载页面" /></div>}>
      <Routes>
        <Route path="/" element={<Navigate to="/management" replace />} />
        <Route path="/management" element={<SkillPage />} />
        <Route path="/management/detail" element={<SkillPage />} />
        <Route path="/management/components" element={<ComponentCenter />} />
        <Route path="/management/components/detail" element={<ComponentDetail />} />
        <Route path="/management/components/create-business-dsl" element={<ComponentAuthoring />} />
        <Route path="/management/components/register-render-component" element={<ComponentAuthoring />} />
        <Route path="/management/components/skill-result-preview" element={<ResultPreview />} />
        <Route path="/management/components/a2ui-catalog" element={<Catalog />} />
        <Route path={A2UI_APPLICATION_ROUTES.list} element={<Applications />} />
        <Route path={A2UI_APPLICATION_ROUTES.create} element={<ApplicationEditor />} />
        <Route path={A2UI_APPLICATION_ROUTES.edit} element={<ApplicationEditor />} />
        <Route path="/management/capabilities" element={<Capabilities />} />
        <Route path="/management/capabilities/create" element={<CapabilityEditor />} />
        <Route path="/management/capabilities/edit" element={<CapabilityEditor />} />
        <Route path="/management/workflows" element={<Workflows />} />
        <Route path="/management/workflows/detail" element={<WorkflowEditor />} />
        <Route path="/management/workflows/:workflowCode" element={<WorkflowEditor />} />
        <Route path="*" element={<Alert type="error" message="页面不存在" />} />
      </Routes>
      </Suspense>
    </main>
  </>;
}

createRoot(rootElement).render(<BrowserRouter><ManagementShell /></BrowserRouter>);
