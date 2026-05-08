import type { CSSProperties } from 'react'

type BrandLogoProps = {
  logoUrl?: string
  size?: number
  color?: string
  className?: string
  style?: CSSProperties
}

export function DefaultBrandLogo({ size = 28, color = '#165DFF' }: { size?: number; color?: string }) {
  return (
    <svg viewBox="0 0 32 32" fill="none" width={size} height={size}>
      <path d="M16 2L30 10V22L16 30L2 22V10L16 2Z" fill={color} />
      <path d="M10 14L16 8L22 14" stroke="white" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round" />
      <line x1="16" y1="8" x2="16" y2="24" stroke="white" strokeWidth="2.5" strokeLinecap="round" />
      <path d="M11 19H21" stroke="white" strokeWidth="2" strokeLinecap="round" />
      <path d="M12 22H20" stroke="white" strokeWidth="1.5" strokeLinecap="round" opacity="0.55" />
    </svg>
  )
}

export default function BrandLogo({ logoUrl, size = 28, color = '#165DFF', className, style }: BrandLogoProps) {
  if (logoUrl) {
    return (
      <img
        src={logoUrl}
        alt="平台 Logo"
        className={className}
        style={{
          width: size,
          height: size,
          objectFit: 'contain',
          display: 'block',
          ...style,
        }}
      />
    )
  }

  return <DefaultBrandLogo size={size} color={color} />
}
