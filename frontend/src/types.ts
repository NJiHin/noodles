export type Depth = 'mentioned' | 'explained' | 'worked_example' | 'practised'
export const DEPTHS: Depth[] = ['mentioned', 'explained', 'worked_example', 'practised']
export type Occurrence = { week: number; depth: Depth; evidence: string[] }
export type Concept = { concept_id: string; name: string; aliases: string[]; description: string; occurrences: Occurrence[] }
export type PassageRef = { slug: string; page: number; week: number }
export type RunStatus = {
  run_id: string; kind: string; status: 'running' | 'done' | 'failed' | 'interrupted'; error: string | null
  done: number; total: number | null; stage: string; started_at: string; ended_at: string | null
}
