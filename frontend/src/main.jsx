import React from 'react';
import { createRoot } from 'react-dom/client';
import App from './App';
import { UIProvider } from './context';
import './rgb-motion.css';

const cardSelector = '.stat-card, .prediction-tile, .search-box';
document.addEventListener('click', event => {
  const card = event.target.closest?.(cardSelector);
  document.querySelector('[data-rgb-clicked]')?.removeAttribute('data-rgb-clicked');
  card?.setAttribute('data-rgb-clicked', '');
});


createRoot(document.getElementById('root')).render(<UIProvider><App /></UIProvider>);
