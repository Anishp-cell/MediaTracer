import { AudioLines, File, FileSpreadsheet, FileText, Film, Image as ImageIcon } from 'lucide-react'

export function FamilyIcon({ family, size = 16, className = '' }: { family: string; size?: number; className?: string }) {
  const combinedClass = `family-icon family-${family} ${className}`.trim()

  switch (family) {
    case 'image':
      return <ImageIcon size={size} className={combinedClass} aria-hidden />
    case 'document':
      return <FileText size={size} className={combinedClass} aria-hidden />
    case 'video':
      return <Film size={size} className={combinedClass} aria-hidden />
    case 'audio':
      return <AudioLines size={size} className={combinedClass} aria-hidden />
    case 'spreadsheet':
      return <FileSpreadsheet size={size} className={combinedClass} aria-hidden />
    default:
      return <File size={size} className={combinedClass} aria-hidden />
  }
}
