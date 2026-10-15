import { StrictMode } from 'react';
import { createRoot } from 'react-dom/client';
import { App } from './App';
import './styles.css';
import './workspace.css';
import './employee-polish.css';
import './work-activity.css';
createRoot(document.getElementById('root')!).render(<StrictMode><App /></StrictMode>);
