import { AudioLines, File, FileSpreadsheet, FileText, Film, Image as ImageIcon } from 'lucide-react'

/** Icon for a media family, declared as a static component (no components created during render). */
export function FamilyIcon({ family, size = 16 }: { family: string; size?: number }) {
  switch (family) {
    case 'image': return <ImageIcon size={size} aria-hidden />
    case 'document': return <FileText size={size} aria-hidden />
    case 'video': return <Film size={size} aria-hidden />
    case 'audio': return <AudioLines size={size} aria-hidden />
    case 'spreadsheet': return <FileSpreadsheet size={size} aria-hidden />
    default: return <File size={size} aria-hidden />
  }
}
