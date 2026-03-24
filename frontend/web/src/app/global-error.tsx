"use client";

export default function GlobalError({
  error,
  reset,
}: {
  error: Error & { digest?: string };
  reset: () => void;
}) {
  return (
    <html lang="en">
      <body className="min-h-screen flex flex-col items-center justify-center bg-gray-50 text-gray-900 px-4">
        <p className="text-6xl font-bold text-gray-200 mb-2">500</p>
        <h1 className="text-xl font-semibold text-gray-800 mb-2">
          Something went wrong
        </h1>
        <p className="text-sm text-gray-500 mb-8 text-center max-w-sm">
          An unexpected error occurred. You can try again or head back to the
          dashboard.
        </p>
        {process.env.NODE_ENV === "development" && error.message && (
          <pre className="text-xs text-red-600 bg-red-50 border border-red-200 rounded-lg p-3 mb-6 max-w-md overflow-auto">
            {error.message}
          </pre>
        )}
        <div className="flex gap-3">
          <button
            onClick={reset}
            className="px-5 py-2.5 bg-blue-600 text-white rounded-xl text-sm font-medium hover:bg-blue-700 transition-colors shadow-sm"
          >
            Try again
          </button>
          <a
            href="/"
            className="px-5 py-2.5 text-gray-600 border border-gray-300 rounded-xl text-sm font-medium hover:bg-gray-50 transition-colors"
          >
            Home
          </a>
        </div>
      </body>
    </html>
  );
}
