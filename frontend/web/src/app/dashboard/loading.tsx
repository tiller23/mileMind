export default function DashboardLoading() {
  return (
    <div className="max-w-4xl mx-auto px-4 py-8 w-full animate-pulse">
      {/* Header skeleton */}
      <div className="flex items-center justify-between mb-8">
        <div>
          <div className="h-7 w-36 bg-gray-200 rounded mb-2" />
          <div className="h-4 w-48 bg-gray-100 rounded" />
        </div>
        <div className="h-10 w-28 bg-gray-200 rounded-xl" />
      </div>

      {/* This Week skeleton */}
      <div className="bg-white border border-gray-200 rounded-xl p-5 shadow-sm mb-6">
        <div className="flex items-center justify-between mb-4">
          <div>
            <div className="h-5 w-24 bg-gray-200 rounded mb-1.5" />
            <div className="h-3.5 w-48 bg-gray-100 rounded" />
          </div>
          <div className="h-4 w-20 bg-gray-100 rounded" />
        </div>
        <div className="grid grid-cols-7 gap-2">
          {Array.from({ length: 7 }).map((_, i) => (
            <div key={i} className="flex flex-col items-center gap-1.5">
              <div className="h-3 w-4 bg-gray-100 rounded" />
              <div className="w-full h-14 bg-gray-100 rounded-lg" />
            </div>
          ))}
        </div>
      </div>

      {/* Plan list skeleton */}
      <div className="h-4 w-24 bg-gray-200 rounded mb-3" />
      <div className="space-y-3">
        {Array.from({ length: 2 }).map((_, i) => (
          <div
            key={i}
            className="bg-white border border-gray-200 rounded-xl p-4 shadow-sm"
          >
            <div className="flex items-center justify-between">
              <div className="flex items-center gap-3">
                <div className="h-5 w-32 bg-gray-200 rounded" />
                <div className="h-4 w-16 bg-gray-100 rounded" />
              </div>
              <div className="h-4 w-24 bg-gray-100 rounded" />
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}
