export type FieldStatus = 'queued' | 'completed' | 'dirty';
export type FieldType = 'text' | 'select' | 'multi-select' | 'file' | 'textarea' | 'checkbox' | 'radio';

export interface FormFieldElement {
  id: string;
  label: string;
  type: FieldType;
  selector: string;
  value: any;
  status: FieldStatus;
}

export interface ChatMessage {
  id: string;
  sender: 'user' | 'agent' | 'system';
  text: string;
  timestamp: Date;
}

export interface AgentProgressState {
  executionQueue: FormFieldElement[];
  currentIndex: number;
  isProcessing: boolean;
  currentUrl: string;
}