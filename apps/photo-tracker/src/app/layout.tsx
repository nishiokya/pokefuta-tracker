import type { Metadata, Viewport } from 'next';
import { Inter } from 'next/font/google';
import './globals.css';

const inter = Inter({ subsets: ['latin'] });

export const metadata: Metadata = {
  title: 'ポケふた写真トラッカー',
  description: 'ポケモンマンホールの訪問記録と写真を管理するアプリ',
  manifest: '/manifest.json',
  icons: {
    apple: '/icon-192.png',
  },
  keywords: ['ポケモン', 'マンホール', 'ポケふた', '写真', '旅行', '記録'],
  authors: [{ name: 'ポケふたトラッカー開発チーム' }],
  creator: 'ポケふたトラッカー',
  publisher: 'ポケふたトラッカー',
  formatDetection: {
    email: false,
    address: false,
    telephone: false,
  },
};

export const viewport: Viewport = {
  width: 'device-width',
  initialScale: 1,
  maximumScale: 1,
  userScalable: false,
  themeColor: '#ff6b6b',
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="ja">
      <head>
        <link rel="apple-touch-icon" href="/icon-192.png" />
        <meta name="apple-mobile-web-app-capable" content="yes" />
        <meta name="apple-mobile-web-app-status-bar-style" content="default" />
        <meta name="apple-mobile-web-app-title" content="ポケふた" />
      </head>
      <body className={`${inter.className} antialiased`}>
        <div id="app" className="min-h-screen bg-gradient-to-br from-pokemon-red via-pokemon-blue to-pokemon-yellow">
          {children}
        </div>
      </body>
    </html>
  );
}