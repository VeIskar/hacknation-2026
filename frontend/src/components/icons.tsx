import type { ReactNode } from 'react'

// Ikony liniowe z wzorców „Jasny urząd”. Zawsze obok tekstu, więc dla czytnika ekranu są ukryte.
function Icon({ size = 18, strokeWidth = 2.2, children }: { size?: number; strokeWidth?: number; children: ReactNode }) {
  return (
    <svg
      className="ikona"
      width={size}
      height={size}
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth={strokeWidth}
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
    >
      {children}
    </svg>
  )
}

interface Props {
  size?: number
}

export function DocumentIcon({ size = 22 }: Props) {
  return (
    <Icon size={size} strokeWidth={2}>
      <path d="M14 3H7a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h10a2 2 0 0 0 2-2V8z" />
      <path d="M14 3v5h5" />
      <path d="M9 13h6M9 17h4" />
    </Icon>
  )
}

export function UploadIcon({ size = 44 }: Props) {
  return (
    <Icon size={size} strokeWidth={1.6}>
      <path d="M14 3H7a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h10a2 2 0 0 0 2-2V8z" />
      <path d="M14 3v5h5" />
      <path d="M12 18v-6" />
      <path d="M9.5 14.5L12 12l2.5 2.5" />
    </Icon>
  )
}

export function CheckIcon({ size = 16 }: Props) {
  return (
    <Icon size={size} strokeWidth={3}>
      <path d="M5 12l4 4 10-10" />
    </Icon>
  )
}

export function LockIcon({ size = 16 }: Props) {
  return (
    <Icon size={size}>
      <rect x="5" y="11" width="14" height="9" rx="2" />
      <path d="M8 11V8a4 4 0 0 1 8 0v3" />
    </Icon>
  )
}

export function ChevronIcon({ size = 18 }: Props) {
  return (
    <Icon size={size}>
      <path d="M6 9l6 6 6-6" />
    </Icon>
  )
}

export function AlertIcon({ size = 18 }: Props) {
  return (
    <Icon size={size} strokeWidth={2.4}>
      <circle cx="12" cy="12" r="9" />
      <path d="M12 7v6" />
      <path d="M12 16.5v.5" />
    </Icon>
  )
}

export function DownloadIcon({ size = 18 }: Props) {
  return (
    <Icon size={size}>
      <path d="M12 4v11" />
      <path d="M7 10l5 5 5-5" />
      <path d="M5 20h14" />
    </Icon>
  )
}
