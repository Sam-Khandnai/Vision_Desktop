// Vision mark: an eight-pointed star built from two squares - the one memorable shape of the interface.
export default function Logo({ size = 28, draw = false }) {
  return (
    <svg className={`logo${draw ? ' logo-draw' : ''}`} width={size} height={size} viewBox="0 0 48 48" fill="none" aria-hidden="true">
      <rect x="9" y="9" width="30" height="30" rx="3" pathLength="1" />
      <rect x="9" y="9" width="30" height="30" rx="3" pathLength="1" transform="rotate(45 24 24)" />
      <rect x="21" y="21" width="6" height="6" rx="1" className="logo-core" transform="rotate(45 24 24)" />
    </svg>
  )
}
