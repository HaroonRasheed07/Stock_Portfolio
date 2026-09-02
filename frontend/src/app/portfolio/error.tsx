"use client";

export default function PortfolioError({
  error,
  reset,
}: {
  error: Error & { digest?: string };
  reset: () => void;
}) {
  return (
    <div className="min-h-[400px] flex flex-col items-center justify-center p-8">
      <div className="text-center space-y-4">
        <p className="text-rose-400 text-sm font-semibold">
          Failed to load portfolio.
        </p>
        <p className="text-slate-500 text-xs">{error.message}</p>
        <button
          onClick={reset}
          className="px-4 py-2 bg-sky-600 hover:bg-sky-500 text-white rounded-lg text-xs font-semibold"
        >
          Try Again
        </button>
      </div>
    </div>
  );
}
