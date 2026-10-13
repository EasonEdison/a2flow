const paths = {
  chevron: 'm6 9 6 6 6-6',
  check: 'm5 12 4 4L19 6',
  stop: 'M7 7h10v10H7z',
  arrow: 'M5 12h14m-6-6 6 6-6 6',
  workflow: 'M12 3v5m0 0H5v7m7-7h7v7M9 3h6M3 15h4v5H3zm14 0h4v5h-4z',
  history: 'M4 5v5h5M4 10a8 8 0 1 1 1 8M12 8v5l3 2',
  chat: 'M5 4h14a2 2 0 0 1 2 2v10a2 2 0 0 1-2 2H9l-6 3V6a2 2 0 0 1 2-2Zm2 5h10M7 13h6',
  bell: 'M18 8a6 6 0 0 0-12 0c0 7-3 7-3 9h18c0-2-3-2-3-9M10 21h4',
  clock: 'M12 3a9 9 0 1 0 0 18 9 9 0 0 0 0-18Zm0 4v5l3 2',
  settings: 'M4 7h16M4 17h16M8 4v6M16 14v6',
  menu: 'M4 6h16M4 12h16M4 18h16',
  close: 'm6 6 12 12M6 18 18 6',
  plus: 'M12 5v14M5 12h14',
  user: 'M16 7a4 4 0 1 1-8 0 4 4 0 0 1 8 0ZM4 21v-2a8 8 0 0 1 16 0v2',
  logout: 'M9 4H4v16h5M10 12h11m-4-4 4 4-4 4',
};

export function Icon({ name, size = 20 }: { name: keyof typeof paths; size?: number }) {
  return <svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="currentColor"
    strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true" focusable="false">
    <path d={paths[name]} />
  </svg>;
}
