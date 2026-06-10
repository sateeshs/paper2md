export default function NotFound() {
  return (
    <div className="text-center py-16 space-y-4">
      <p className="text-6xl font-bold text-zinc-200 dark:text-zinc-700">404</p>
      <p className="text-zinc-500">Page not found.</p>
      <a href="/" className="text-sm text-blue-600 hover:underline">
        ← Back to home
      </a>
    </div>
  );
}
