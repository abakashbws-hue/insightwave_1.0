
import { FirestoreDocument } from '../services/firestore-data.service';

export const TOOL_USAGE_COLLECTION = 'toolUsageHistory';

export interface ToolUsageHistory extends FirestoreDocument {
  toolName: string;
  usageType: string;
  customerName?: string;
  projectName?: string;
  description?: string;
  createdBy: string;
  createdAt: string;
  isAgentRun?: boolean;
}
