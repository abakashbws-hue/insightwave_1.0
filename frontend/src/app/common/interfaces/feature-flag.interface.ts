import { FirestoreDocument } from '../services/firestore-data.service';

export const FEATURE_FLAG_COLLECTION = 'featureFlags';

export interface FeatureFlag extends FirestoreDocument {
  isEnabled?: boolean;
}
