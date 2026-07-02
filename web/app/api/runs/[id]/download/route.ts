// Download proxy for a run's delivered video.
//
// The video lives at a cross-origin InsForge storage URL (`runs.final_url`). A
// plain `<a download>` can't force a filename across origins, and a client-side
// fetch would hit CORS — so the Download button links here and this route does the
// work server-side: look up the run with the admin InsForge client, fetch the MP4,
// and stream it back as an attachment with a clean Filmo filename.
//
// Returns 404 when the run isn't delivered or has no final_url.
import { NextResponse } from 'next/server'
import { adminClient } from '../../../../../lib/insforge'
import { isDelivered } from '../../../../../lib/types'

export const dynamic = 'force-dynamic'

export async function GET(
  req: Request,
  { params }: { params: Promise<{ id: string }> },
) {
  const { id } = await params
  if (!id) {
    return new NextResponse('Missing run id', { status: 400 })
  }
  // `?cut=original` forces the pre-edit render; default prefers the edited cut below.
  const wantOriginal = new URL(req.url).searchParams.get('cut') === 'original'

  // ── IDOR note (ACCEPTED hackathon risk) ───────────────────────────────────
  // This route streams a delivered run's MP4 by id WITHOUT an ownership check, so
  // anyone who knows a run id can fetch its video. We deliberately do NOT gate it
  // on `verifyUser(...) && run.user_id === caller.id`: the Download button is a
  // plain GET <a href> (a top-level browser navigation), and this app carries the
  // InsForge access token in client memory (SDK tokenManager), NOT in a cookie —
  // so the navigation sends no Authorization header and there is no session cookie
  // for the route to read. An ownership gate would therefore 404 the legitimate
  // owner's own download, which is worse than the exposure. The exposure is bounded:
  // run ids are unguessable UUIDs and the only thing returned is the marketing-video
  // output the user asked Filmo to produce (no PII, no account data). If this ever
  // ships beyond the hackathon, move auth onto a short-lived signed download URL
  // (or set an httpOnly session cookie) so the GET can be gated without breaking it.
  //
  // Admin client bypasses RLS so the route can resolve the run's final_url. We only
  // expose the bytes of a delivered video; no user data is returned.
  const db = adminClient()
  const { data, error } = await db.database
    .from('runs')
    .select('id, status, final_url, edited_url')
    .eq('id', id)
    .maybeSingle()

  if (error || !data) {
    return new NextResponse('Run not found', { status: 404 })
  }

  const run = data as {
    id: string
    status?: string | null
    final_url?: string | null
    edited_url?: string | null
  }
  // `completed_with_warnings` ships a real video too — gate on delivered-ish, not
  // strictly 'delivered', so its Download button doesn't 404.
  if (!isDelivered(run.status) || !run.final_url) {
    return new NextResponse('No video available for this run', { status: 404 })
  }

  // THE CUT THAT DOWNLOADS = THE CUT THE PAGE PLAYS. When an editor Export has
  // produced an edited cut (runs.edited_url), the run page shows it FIRST — so the
  // Download button must serve the SAME cut, not silently hand back the pre-edit
  // render (users lost their saved edits on download). `?cut=original` opts out.
  const src = (!wantOriginal && run.edited_url) || run.final_url
  const cutTag = src === run.edited_url ? '-edited' : ''

  // Server-side fetch the MP4 from InsForge storage (no CORS, no exposed URL).
  let upstream: Response
  try {
    upstream = await fetch(src, { cache: 'no-store' })
  } catch {
    return new NextResponse('Failed to fetch the video', { status: 502 })
  }
  if (!upstream.ok || !upstream.body) {
    return new NextResponse('Failed to fetch the video', { status: 502 })
  }

  const headers = new Headers()
  headers.set('Content-Type', 'video/mp4')
  headers.set('Content-Disposition', `attachment; filename="filmo-${run.id}${cutTag}.mp4"`)
  const len = upstream.headers.get('content-length')
  if (len) headers.set('Content-Length', len)
  headers.set('Cache-Control', 'no-store')

  // Stream the upstream body straight through to the client.
  return new NextResponse(upstream.body, { status: 200, headers })
}
