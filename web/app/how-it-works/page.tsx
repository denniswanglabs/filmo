// /how-it-works — a chapter of the landing, in the landing's own grammar.
// The page itself stays a server component so the metadata ships with the
// document; the chapter (night ground, display type, reveals) is the client
// component beside this file. The old version of this route stacked the
// retired light-blue marketing shell (FloatingNav / panel sections /
// ClosingCTA / SiteFooter) — that shell is gone from the product.
import HowItWorksChapter from './HowItWorksChapter'

export const metadata = {
  title: 'How it works — Filmo',
  description:
    'How Filmo turns a URL into a finished launch film: it reads the pages a buyer opens, plans the cut from your own words, films your product in a real browser, cuts it on your palette, reviews the film back, and ships an MP4 you can re-cut by chat.',
}

export default function HowItWorksPage() {
  return <HowItWorksChapter />
}
