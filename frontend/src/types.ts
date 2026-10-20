export type Depth = 'mentioned' | 'explained' | 'worked_example' | 'practised'
export const DEPTHS: Depth[] = ['mentioned', 'explained', 'worked_example', 'practised']
export type Occurrence = { week: number; depth: Depth; evidence: string[] }
export type Concept = { concept_id: string; name: string; aliases: string[]; description: string; occurrences: Occurrence[] }
export type PassageRef = { slug: string; page: number; week: number }
export type RunStatus = {
  run_id: string; kind: string; status: 'running' | 'done' | 'failed' | 'interrupted'; error: string | null
  done: number; total: number | null; stage: string; started_at: string; ended_at: string | null
}
export type QType = 'mcq' | 'true_false' | 'short' | 'numeric' | 'open' | 'code'
export const QTYPES: QType[] = ['mcq', 'true_false', 'short', 'numeric', 'open', 'code']
export type Question = { question_id: string; text: string; options: string[] | null; type: QType; marking_material: string | null; flags?: string[] }
export type Assessment = {
  assessment_id: string; week_cutoff: number; current_format: string; files: Record<string, string>
  state: 'none' | 'running' | 'failed' | 'interrupted' | 'draft' | 'confirmed'; run: RunStatus | null
  questions: Question[]; unmatched_marking_material: string[]
}
export const FORMAT_LABEL: Record<string, string> = { take_home: 'take-home', online_quiz: 'online quiz', invigilated_exam: 'invigilated exam' }
export type Cited = { passage_id: string; course?: string; version_id?: string; week?: number; filename?: string; slug?: string; page?: number; text?: string }
export type Step = { step_id: string; claim: string; source: 'course' | 'prerequisite' | 'assumed_knowledge' | 'none'; evidence: Cited[]; reason: string | null; accepted_id: number | null }
export type ReviewQuestion = {
  question_id: string; assessment_id: string; text: string; options: string[] | null; type: QType; week_cutoff: number; current_format: string
  answer: { final_answer: string | null; steps: Step[] } | null; gap: boolean
}
export type ReviewResp = { course_code: string; run: RunStatus | null; prerequisite: string | null; questions: ReviewQuestion[] }
