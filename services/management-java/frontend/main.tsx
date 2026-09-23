import React, { lazy, Suspense } from 'react';
import ReactDOM from 'react-dom';
import { BrowserRouter, Link, Navigate, Route, Routes } from 'react-router-dom';
import { Alert, Spin } from 'antd';
import 'antd/dist/antd.css';
import './management.less';
import { A2UI_APPLICATION_ROUTES } from './a2uiCatalogContracts';

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

ReactDOM.render(
  <BrowserRouter>
    <nav className="management-navigation" aria-label="管理台导航">
      <strong>A2Flow</strong><Link to="/management">Skill</Link><Link to="/management/capabilities">能力</Link><Link to="/management/components">A2UI / 组件</Link><Link to="/management/workflows">Workflow</Link>
    </nav>
    <main className="management-content"><Suspense fallback={<Spin tip="加载页面" />}>
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
    </Suspense></main>
  </BrowserRouter>, document.getElementById('root'),
);
