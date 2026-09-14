import { ProjectDetail } from "@/components/project-detail";

export default async function ProjectSecurityPage({ params }: { params: Promise<{ address: string }> }) { const { address } = await params; return <ProjectDetail address={address} tab="Security" />; }
