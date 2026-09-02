export default function StockDetailLoading() {
  return (
    <div className="min-h-[400px] flex flex-col items-center justify-center p-8">
      <div className="w-6 h-6 border-2 border-sky-400 border-t-transparent rounded-full animate-spin" />
      <p className="text-slate-400 text-xs mt-3">Loading...</p>
    </div>
  );
}
