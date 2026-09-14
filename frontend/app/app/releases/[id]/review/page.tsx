import { ReleaseDetail } from "@/components/release-detail";

export default async function ReleaseReviewPage({ params }: { params: Promise<{ id: string }> }) { const { id } = await params; return <ReleaseDetail id={id} tab="Semantic Review" />; }
