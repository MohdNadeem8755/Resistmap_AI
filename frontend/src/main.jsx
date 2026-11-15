import React from 'react';
import { createRoot } from 'react-dom/client';
import App from './App';
import { UIProvider } from './context';

createRoot(document.getElementById('root')).render(<UIProvider><App /></UIProvider>);
