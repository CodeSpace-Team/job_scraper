export default function SearchBar({ value, onChange }) {
  return (
    <input
      type="search"
      value={value}
      onChange={(e) => onChange(e.target.value)}
      placeholder="Search by title, company or keyword..."
      aria-label="Search jobs"
      className="w-full rounded-md border border-neutral-300 px-4 py-2 text-sm shadow-sm focus:border-codespace-teal focus:outline-none focus:ring-1 focus:ring-codespace-teal"
    />
  )
}