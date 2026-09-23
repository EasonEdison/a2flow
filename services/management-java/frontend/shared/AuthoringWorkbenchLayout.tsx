import React from 'react';

export type AuthoringRailView = 'chat' | 'review';

interface AuthoringWorkbenchLayoutProps {
  children: React.ReactNode;
  chat: React.ReactNode;
  review?: React.ReactNode;
  reviewCount?: number;
  railOpen: boolean;
  railView: AuthoringRailView;
  onRailOpenChange: (open: boolean) => void;
  onRailViewChange: (view: AuthoringRailView) => void;
  railTitle?: string;
  railSubtitle?: string;
  className?: string;
}

const AuthoringWorkbenchLayout: React.FC<AuthoringWorkbenchLayoutProps> = ({ children, className = "" }) => (
  <div className={`authoring-workbench-layout rail-closed ${className}`.trim()}>
    <main className="authoring-workbench-main">{children}</main>
  </div>
);

export default AuthoringWorkbenchLayout;
