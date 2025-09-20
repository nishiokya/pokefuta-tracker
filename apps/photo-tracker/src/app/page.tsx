import Link from 'next/link';
import { Camera, Map, History, Settings } from 'lucide-react';

export default function HomePage() {
  return (
    <div className="container-pokemon min-h-screen safe-area-inset">
      {/* Header */}
      <header className="py-8 text-center">
        <h1 className="text-4xl font-bold text-white text-shadow-pokemon mb-2">
          🗾 ポケふた
        </h1>
        <p className="text-white/90 text-lg">
          写真トラッカー
        </p>
      </header>

      {/* Quick Stats */}
      <div className="card-pokemon p-6 mb-8">
        <div className="grid grid-cols-3 gap-4 text-center">
          <div>
            <div className="text-2xl font-bold text-pokemon-red">0</div>
            <div className="text-sm text-pokemon-darkBlue/70">訪問済み</div>
          </div>
          <div>
            <div className="text-2xl font-bold text-pokemon-blue">422</div>
            <div className="text-sm text-pokemon-darkBlue/70">総マンホール</div>
          </div>
          <div>
            <div className="text-2xl font-bold text-pokemon-yellow">0</div>
            <div className="text-sm text-pokemon-darkBlue/70">写真</div>
          </div>
        </div>
      </div>

      {/* Main Actions */}
      <div className="space-y-4 mb-8">
        <Link
          href="/upload"
          className="block w-full btn-pokemon text-center py-6"
        >
          <Camera className="w-8 h-8 mx-auto mb-2" />
          <div className="text-lg font-bold">写真を登録する</div>
          <div className="text-sm opacity-90">新しい訪問記録を追加</div>
        </Link>

        <div className="grid grid-cols-2 gap-4">
          <Link
            href="/map"
            className="btn-pokemon-secondary text-center py-4 block"
          >
            <Map className="w-6 h-6 mx-auto mb-1" />
            <div className="font-semibold">マップ</div>
          </Link>

          <Link
            href="/visits"
            className="btn-pokemon-secondary text-center py-4 block"
          >
            <History className="w-6 h-6 mx-auto mb-1" />
            <div className="font-semibold">履歴</div>
          </Link>
        </div>
      </div>

      {/* Recent Visits */}
      <div className="card-pokemon p-6 mb-8">
        <h2 className="text-xl font-bold mb-4 text-pokemon-darkBlue">
          最近の訪問
        </h2>
        <div className="text-center py-8 text-pokemon-darkBlue/60">
          まだ訪問記録がありません
          <br />
          写真を登録して記録を始めましょう！
        </div>
      </div>

      {/* Nearby Suggestions */}
      <div className="card-pokemon p-6 mb-20">
        <h2 className="text-xl font-bold mb-4 text-pokemon-darkBlue">
          近くの未訪問マンホール
        </h2>
        <div className="text-center py-8 text-pokemon-darkBlue/60">
          位置情報を有効にすると
          <br />
          近くのマンホールを表示します
        </div>
        <button className="btn-pokemon-secondary w-full mt-4">
          位置情報を許可
        </button>
      </div>

      {/* Bottom Navigation */}
      <nav className="nav-pokemon">
        <div className="flex justify-around items-center max-w-md mx-auto">
          <Link href="/" className="nav-item active">
            <div className="w-6 h-6 mb-1">🏠</div>
            <span className="text-xs">ホーム</span>
          </Link>
          <Link href="/map" className="nav-item">
            <Map className="w-6 h-6 mb-1" />
            <span className="text-xs">マップ</span>
          </Link>
          <Link href="/upload" className="nav-item">
            <Camera className="w-6 h-6 mb-1" />
            <span className="text-xs">登録</span>
          </Link>
          <Link href="/visits" className="nav-item">
            <History className="w-6 h-6 mb-1" />
            <span className="text-xs">履歴</span>
          </Link>
          <Link href="/settings" className="nav-item">
            <Settings className="w-6 h-6 mb-1" />
            <span className="text-xs">設定</span>
          </Link>
        </div>
      </nav>
    </div>
  );
}