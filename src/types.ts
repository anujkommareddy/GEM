export interface Shot {
  id: string;
  description: string;
  visual: string;
  camera: string;
  mood: string;
  duration: number;
  imagePrompt?: string;
  videoPrompt?: string;
  imageUrl?: string;
  imageStatus: "pending" | "generating" | "approved" | "rejected" | "failed";
  videoStatus: "pending" | "generating" | "done" | "failed";
  videoUrl?: string;
  outputPath?: string;
}

export interface Scene {
  id: string;
  title: string;
  description: string;
  shots: Shot[];
}

export interface Project {
  name: string;
  concept: string;
  developedConcept?: string;
  logline?: string;
  tone?: string;
  style?: string;
  targetDuration?: string;
  scenes: Scene[];
  stage: "develop" | "plan" | "look-dev" | "prompt-review" | "generate" | "complete";
  createdAt: string;
  updatedAt: string;
}

export function createProject(name: string, concept: string): Project {
  return {
    name,
    concept,
    scenes: [],
    stage: "develop",
    createdAt: new Date().toISOString(),
    updatedAt: new Date().toISOString(),
  };
}
