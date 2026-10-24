import { CoinPageClient } from '@/components/coin/coin-page-client';

export default async function CoinPage({ params }: { params: Promise<{ symbol: string }> }) {
  const { symbol } = await params;
  return <CoinPageClient symbol={decodeURIComponent(symbol).toUpperCase()} />;
}
