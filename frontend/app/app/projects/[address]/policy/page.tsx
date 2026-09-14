import { ProjectDetail } from "@/components/project-detail";

export default async function ProjectPolicyPage({ params }: { params: Promise<{ address: string }> }) { const { address } = await params; return <ProjectDetail address={address} tab="Policy" />; }
